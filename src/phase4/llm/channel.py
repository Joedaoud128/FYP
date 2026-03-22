from __future__ import annotations

from pathlib import Path

from phase4.domain.interfaces import ExecutionEngine, LlmProposalGuard, LlmRemediationProvider, LlmRemediator
from phase4.domain.models import (
    ClassificationResult,
    ErrorRecord,
    ExecutionResult,
    LlmProposal,
    LlmProposalType,
)


class LlmRemediationChannel(LlmRemediator):
    def __init__(
        self,
        provider: LlmRemediationProvider,
        guard: LlmProposalGuard,
        execution_engine: ExecutionEngine,
        workspace_root: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self._provider = provider
        self._guard = guard
        self._execution_engine = execution_engine
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self._timeout_seconds = timeout_seconds

    def remediate(
        self,
        command: list[str],
        execution_result: ExecutionResult,
        parsed_error: ErrorRecord | None,
        classification: ClassificationResult | None,
    ) -> ExecutionResult:
        proposal = self._provider.generate(command, execution_result, parsed_error, classification)
        if proposal is None:
            return ExecutionResult(
                command=["llm", "proposal"],
                exit_code=1,
                stdout="",
                stderr="LLM remediation provider returned no valid proposal.",
            )

        if proposal.proposal_type == LlmProposalType.SCRIPT_PATCH:
            return self._apply_script_patch(command, proposal)

        if proposal.proposal_type == LlmProposalType.COMMAND:
            return self._execute_guarded_command(proposal)

        return ExecutionResult(
            command=["llm", "proposal"],
            exit_code=1,
            stdout="",
            stderr="Unsupported LLM proposal type.",
        )

    def _execute_guarded_command(self, proposal: LlmProposal) -> ExecutionResult:
        if proposal.command is None or len(proposal.command) == 0:
            return ExecutionResult(
                command=["llm", "command"],
                exit_code=1,
                stdout="",
                stderr="LLM command proposal is empty.",
            )

        decision = self._guard.evaluate_command(proposal.command)
        if not decision.allowed:
            return ExecutionResult(
                command=proposal.command,
                exit_code=1,
                stdout="",
                stderr=f"Guardrails blocked LLM command: {decision.reason}",
            )

        safe_command = decision.normalized_command or proposal.command
        return self._execution_engine.run(safe_command, timeout_seconds=self._timeout_seconds)

    def _apply_script_patch(self, command: list[str], proposal: LlmProposal) -> ExecutionResult:
        target = self._resolve_target_file(command, proposal)
        if target is None:
            return ExecutionResult(
                command=["llm", "script_patch"],
                exit_code=1,
                stdout="",
                stderr="Unable to resolve target file for LLM script patch.",
            )

        if proposal.script_content is None:
            return ExecutionResult(
                command=["llm", "script_patch", str(target)],
                exit_code=1,
                stdout="",
                stderr="LLM script patch content is missing.",
            )

        if not self._is_within_workspace(target):
            return ExecutionResult(
                command=["llm", "script_patch", str(target)],
                exit_code=1,
                stdout="",
                stderr="LLM script patch target escapes workspace.",
            )

        original_content = target.read_text(encoding="utf-8") if target.exists() else ""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposal.script_content, encoding="utf-8")

        compile_result = self._execution_engine.run(
            ["python", "-m", "py_compile", str(target)],
            timeout_seconds=self._timeout_seconds,
        )
        if compile_result.exit_code != 0:
            target.write_text(original_content, encoding="utf-8")
            return ExecutionResult(
                command=["llm", "script_patch", str(target)],
                exit_code=1,
                stdout="",
                stderr=f"LLM patch failed compile validation and was rolled back. {compile_result.stderr.strip()}",
            )

        return ExecutionResult(
            command=["llm", "script_patch", str(target)],
            exit_code=0,
            stdout=f"Applied LLM script patch to {target}",
            stderr="",
        )

    def _resolve_target_file(self, command: list[str], proposal: LlmProposal) -> Path | None:
        if proposal.target_file:
            candidate = Path(proposal.target_file)
            return candidate if candidate.is_absolute() else (self._workspace_root / candidate)

        if len(command) >= 2:
            script_path = Path(command[1])
            return script_path if script_path.is_absolute() else (self._workspace_root / script_path)

        return None

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self._workspace_root)
            return True
        except ValueError:
            return False
