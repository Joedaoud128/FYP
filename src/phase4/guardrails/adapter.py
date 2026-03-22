from __future__ import annotations

import os
import shlex
from pathlib import Path

from phase4.domain.interfaces import CorrectiveActionExecutor
from phase4.domain.models import CorrectiveAction, ExecutionResult


class GuardrailsActionExecutorAdapter(CorrectiveActionExecutor):
    def __init__(
        self,
        delegate: CorrectiveActionExecutor,
        workspace_root: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    def execute(self, action: CorrectiveAction) -> ExecutionResult:
        if action.command is None:
            return self._delegate.execute(action)

        decision = self._evaluate_guardrails(action.command)
        if not decision.allowed:
            return ExecutionResult(
                command=action.command,
                exit_code=1,
                stdout="",
                stderr=f"Guardrails blocked action: {decision.reason}",
            )

        return self._delegate.execute(action)

    def _evaluate_guardrails(self, command: list[str]):
        os.environ["AGENT_WORKSPACE"] = str(self._workspace_root)
        from guardrails_container_eval import guardrails

        guardrails.WORKSPACE_ROOT = self._workspace_root
        canonical = self._to_guardrails_cmdline(command)
        return guardrails.gate(canonical)

    def _to_guardrails_cmdline(self, command: list[str]) -> str:
        if len(command) >= 4 and command[1:4] == ["-m", "pip", "install"]:
            package = command[4] if len(command) > 4 else ""
            return shlex.join(["python", "-m", "pip", "install", package])

        if len(command) >= 3 and command[1:3] == ["-m", "py_compile"]:
            return shlex.join(["python", "-m", "py_compile", command[3]])

        if len(command) >= 2 and command[0].lower().endswith("python.exe"):
            return shlex.join(["python", command[1]])

        return shlex.join(command)
