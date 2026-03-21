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
from phase4.actions.planner import DeterministicActionPlanner
from phase4.classifier.deterministic import DeterministicPythonErrorClassifier
from phase4.domain.models import ExecutionResult
from phase4.runtime.noop_journal import NoOpActionJournal
from phase4.parsing.stderr_parser import PythonStderrParser
from phase4.workflow.reactive import ReactiveDebugWorkflow


class FakeExecutionEngine:
    def __init__(self, scenario: str = "missing_module") -> None:
        self.commands: list[list[str]] = []
        self._script_run_count = 0
        self._scenario = scenario

    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        self.commands.append(command)

        is_pip_install = len(command) >= 4 and command[1:4] == ["-m", "pip", "install"]
        if is_pip_install:
            return ExecutionResult(command=command, exit_code=0, stdout="installed", stderr="")

        self._script_run_count += 1
        if self._script_run_count == 1 and self._scenario == "missing_module":
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'yfinance'",
            )

        if self._script_run_count == 1 and self._scenario == "indentation":
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=(
                    '  File "script.py", line 2\n'
                    "    \tprint('bad')\n"
                    "IndentationError: unexpected indent"
                ),
            )

        if self._script_run_count == 1 and self._scenario == "file_not_found":
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr="FileNotFoundError: [Errno 2] No such file or directory: 'data/input.txt'",
            )

        if self._scenario == "repeat_error":
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr="ModuleNotFoundError: No module named 'yfinance'",
            )

        return ExecutionResult(command=command, exit_code=0, stdout="ok", stderr="")


class TestReactiveWorkflow(unittest.TestCase):
    def test_workflow_applies_pip_install_then_succeeds(self) -> None:
        engine = FakeExecutionEngine()
        workflow = ReactiveDebugWorkflow(
            execution_engine=engine,
            parser=PythonStderrParser(),
            classifier=DeterministicPythonErrorClassifier(),
            action_planner=DeterministicActionPlanner("python"),
            action_executor=GuardedActionExecutor(engine),
            action_journal=NoOpActionJournal(),
            max_iterations=2,
        )

        result = workflow.run(["python", "-c", "import yfinance"])

        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(result.logs), 2)
        self.assertIn(["python", "-m", "pip", "install", "yfinance"], engine.commands)

    def test_workflow_plans_indentation_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            script = Path(tmp_dir) / "script.py"
            script.write_text("print('ok')\n\tprint('bad')\n", encoding="utf-8")

            engine = FakeExecutionEngine(scenario="indentation")
            workflow = ReactiveDebugWorkflow(
                execution_engine=engine,
                parser=PythonStderrParser(),
                classifier=DeterministicPythonErrorClassifier(),
                action_planner=DeterministicActionPlanner("python", workspace_root=tmp_dir),
                action_executor=GuardedActionExecutor(engine),
                action_journal=NoOpActionJournal(),
                max_iterations=2,
            )

            result = workflow.run(["python", str(script)])

            self.assertTrue(result.success)
            self.assertEqual(result.logs[0].action.action_type.value, "normalize_indentation")

    def test_workflow_denies_file_not_found_auto_create_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = FakeExecutionEngine(scenario="file_not_found")
            workflow = ReactiveDebugWorkflow(
                execution_engine=engine,
                parser=PythonStderrParser(),
                classifier=DeterministicPythonErrorClassifier(),
                action_planner=DeterministicActionPlanner("python", workspace_root=tmp_dir),
                action_executor=GuardedActionExecutor(engine),
                action_journal=NoOpActionJournal(),
                max_iterations=2,
            )

            result = workflow.run(["python", "app.py"])

            self.assertFalse(result.success)
            self.assertEqual(result.failure_reason, "Classification confidence below policy threshold.")

    def test_workflow_blocks_repeated_same_action(self) -> None:
        engine = FakeExecutionEngine(scenario="repeat_error")
        workflow = ReactiveDebugWorkflow(
            execution_engine=engine,
            parser=PythonStderrParser(),
            classifier=DeterministicPythonErrorClassifier(),
            action_planner=DeterministicActionPlanner("python"),
            action_executor=GuardedActionExecutor(engine),
            action_journal=NoOpActionJournal(),
            max_iterations=3,
        )

        result = workflow.run(["python", "-c", "import yfinance"])

        self.assertFalse(result.success)
        self.assertEqual(result.failure_reason, "Repeated corrective action blocked by idempotency policy.")


if __name__ == "__main__":
    unittest.main()
