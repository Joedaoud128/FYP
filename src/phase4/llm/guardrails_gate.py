from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from phase4.domain.interfaces import LlmProposalGuard
from phase4.domain.models import GuardrailDecision


class GuardrailsProposalGuard(LlmProposalGuard):
    def __init__(self, workspace_root: str | None = None) -> None:
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    def evaluate_command(self, command: list[str]) -> GuardrailDecision:
        os.environ["AGENT_WORKSPACE"] = str(self._workspace_root)
        project_root = Path(__file__).resolve().parents[3]
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        from guardrails_container_eval import guardrails

        guardrails.WORKSPACE_ROOT = self._workspace_root
        decision = guardrails.gate(self._canonicalize(command))
        return GuardrailDecision(
            allowed=decision.allowed,
            reason=decision.reason,
            normalized_command=decision.normalized_argv,
        )

    def _canonicalize(self, command: list[str]) -> str:
        if len(command) >= 4 and command[1:4] == ["-m", "pip", "install"]:
            package = command[4] if len(command) > 4 else ""
            return shlex.join(["python", "-m", "pip", "install", package])
        if len(command) >= 3 and command[1:3] == ["-m", "py_compile"]:
            return shlex.join(["python", "-m", "py_compile", command[3]])
        if command and command[0].lower().endswith("python.exe"):
            if len(command) >= 2:
                return shlex.join(["python", command[1]])
        return shlex.join(command)
