from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.domain.models import ActionType, CorrectiveAction, ExecutionResult
from phase4.guardrails.adapter import GuardrailsActionExecutorAdapter


class DelegateExecutor:
    def __init__(self) -> None:
        self.calls: list[CorrectiveAction] = []

    def execute(self, action: CorrectiveAction) -> ExecutionResult:
        self.calls.append(action)
        return ExecutionResult(command=action.command or ["internal"], exit_code=0, stdout="ok", stderr="")


class TestGuardrailsAdapter(unittest.TestCase):
    def test_allows_constrained_pip_install(self) -> None:
        delegate = DelegateExecutor()
        adapter = GuardrailsActionExecutorAdapter(delegate, workspace_root=str(PROJECT_ROOT))

        action = CorrectiveAction(
            action_type=ActionType.PIP_INSTALL,
            command=[sys.executable, "-m", "pip", "install", "yfinance"],
            arguments={},
            safe_to_auto_execute=True,
            description="Install yfinance",
        )

        result = adapter.execute(action)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(delegate.calls), 1)

    def test_blocks_disallowed_python_shape(self) -> None:
        delegate = DelegateExecutor()
        adapter = GuardrailsActionExecutorAdapter(delegate, workspace_root=str(PROJECT_ROOT))

        action = CorrectiveAction(
            action_type=ActionType.PIP_INSTALL,
            command=["python", "-c", "print('x')"],
            arguments={},
            safe_to_auto_execute=True,
            description="Unsafe python shape",
        )

        result = adapter.execute(action)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Guardrails blocked action", result.stderr)
        self.assertEqual(len(delegate.calls), 0)

    def test_internal_actions_bypass_shell_guardrails(self) -> None:
        delegate = DelegateExecutor()
        adapter = GuardrailsActionExecutorAdapter(delegate, workspace_root=str(PROJECT_ROOT))

        action = CorrectiveAction(
            action_type=ActionType.NORMALIZE_INDENTATION,
            command=None,
            arguments={"file_path": "x.py", "line_number": 1},
            safe_to_auto_execute=True,
            description="internal",
        )

        result = adapter.execute(action)

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(delegate.calls), 1)


if __name__ == "__main__":
    unittest.main()
