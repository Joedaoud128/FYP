from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.actions.executor import GuardedActionExecutor
from phase4.domain.models import ActionType, CorrectiveAction, ExecutionResult


class DummyExecutionEngine:
    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        return ExecutionResult(command=command, exit_code=0, stdout="ok", stderr="")


class FailingCompileEngine:
    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        is_compile = len(command) >= 3 and command[1:3] == ["-m", "py_compile"]
        if is_compile:
            return ExecutionResult(command=command, exit_code=1, stdout="", stderr="compile error")
        return ExecutionResult(command=command, exit_code=0, stdout="ok", stderr="")


class TestActionExecutor(unittest.TestCase):
    def test_normalize_indentation_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "bad.py"
            target.write_text("\tprint('x')\n", encoding="utf-8")

            action = CorrectiveAction(
                action_type=ActionType.NORMALIZE_INDENTATION,
                command=None,
                arguments={"file_path": str(target), "line_number": 1},
                safe_to_auto_execute=True,
                description="Normalize indentation",
            )

            executor = GuardedActionExecutor(DummyExecutionEngine())
            result = executor.execute(action)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "    print('x')\n")

    def test_create_missing_file_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "data" / "input.txt"

            action = CorrectiveAction(
                action_type=ActionType.CREATE_MISSING_FILE,
                command=None,
                arguments={"file_path": str(target)},
                safe_to_auto_execute=True,
                description="Create file",
            )

            executor = GuardedActionExecutor(DummyExecutionEngine())
            result = executor.execute(action)

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(target.exists())
            self.assertTrue(target.is_file())

    def test_normalize_indentation_rolls_back_on_compile_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "bad.py"
            original = "\tprint('x')\n"
            target.write_text(original, encoding="utf-8")

            action = CorrectiveAction(
                action_type=ActionType.NORMALIZE_INDENTATION,
                command=None,
                arguments={"file_path": str(target), "line_number": 1},
                safe_to_auto_execute=True,
                description="Normalize indentation",
            )

            executor = GuardedActionExecutor(FailingCompileEngine())
            result = executor.execute(action)

            self.assertEqual(result.exit_code, 1)
            self.assertIn("Rolled back changes", result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
