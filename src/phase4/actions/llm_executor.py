from __future__ import annotations

import importlib.util
from pathlib import Path
import shlex
from typing import Any

from phase4.domain.interfaces import ExecutionEngine
from phase4.domain.models import ExecutionResult, LlmFallbackPlan


class UnrestrictedLlmFallbackExecutor:
    def __init__(
        self,
        execution_engine: ExecutionEngine,
        timeout_seconds: int = 300,
        workspace_root: str | None = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._timeout_seconds = timeout_seconds
        self._workspace_root = str(Path(workspace_root).resolve()) if workspace_root else str(Path.cwd().resolve())
        self._guardrails_engine = self._load_guardrails_engine()

    def execute_plan(self, plan: LlmFallbackPlan) -> ExecutionResult:
        for write in plan.file_writes:
            target = Path(write.file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(write.content, encoding="utf-8")

        if not plan.commands:
            return ExecutionResult(
                command=["internal", "llm_fallback", "file_writes_only"],
                exit_code=0,
                stdout="Applied LLM file writes.",
                stderr="",
            )

        last_result = ExecutionResult(command=[], exit_code=0, stdout="", stderr="")
        for command in plan.commands:
            validation = self._validate_llm_command(command.command)
            if validation["status"] != "PASS":
                return ExecutionResult(
                    command=command.command,
                    exit_code=1,
                    stdout="",
                    stderr=(
                        "Guardrails blocked LLM command. "
                        f"status={validation['status']}; "
                        f"reason={validation.get('reason')}; "
                        f"failing_rule_id={validation.get('failing_rule_id')}"
                    ),
                )

            token_array = validation.get("token_array") or command.command
            if not isinstance(token_array, list) or not all(isinstance(token, str) for token in token_array):
                return ExecutionResult(
                    command=command.command,
                    exit_code=1,
                    stdout="",
                    stderr="Guardrails returned an invalid token_array.",
                )

            last_result = self._execution_engine.run(token_array, timeout_seconds=self._timeout_seconds)
            if last_result.exit_code != 0:
                return last_result
        return last_result

    def _validate_llm_command(self, command: list[str]) -> dict[str, Any]:
        raw_command = shlex.join(command)
        request = {
            "caller_service": "debugging",
            "raw_command": raw_command,
            "working_dir": self._workspace_root,
        }
        return self._guardrails_engine.validate(request)

    @staticmethod
    def _load_guardrails_engine():
        project_root = Path(__file__).resolve().parents[3]
        module_path = project_root / "FYP-guardrails-module" / "guardrails_engine.py"
        config_path = project_root / "FYP-guardrails-module" / "guardrails_config.yaml"

        if not module_path.exists():
            raise FileNotFoundError(f"Guardrails engine module not found: {module_path}")
        if not config_path.exists():
            raise FileNotFoundError(f"Guardrails config not found: {config_path}")

        spec = importlib.util.spec_from_file_location("fyp_guardrails_engine", str(module_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load guardrails engine from {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        engine_cls = getattr(module, "GuardrailsEngine", None)
        if engine_cls is None:
            raise ImportError("GuardrailsEngine class not found in guardrails module")

        return engine_cls(str(config_path))
