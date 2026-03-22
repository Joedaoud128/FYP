from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.actions.llm_executor import UnrestrictedLlmFallbackExecutor
from phase4.domain.models import ExecutionResult, LlmFallbackPlan, LlmFileWrite, LlmShellCommand


class FakeExecutionEngine:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        _ = timeout_seconds
        self.commands.append(command)
        return ExecutionResult(command=command, exit_code=0, stdout="ok", stderr="")


class TestUnrestrictedLlmFallbackExecutor(unittest.TestCase):
    def test_executes_commands_and_file_writes(self) -> None:
        engine = FakeExecutionEngine()
        executor = UnrestrictedLlmFallbackExecutor(engine)

        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "fixed.py"
            plan = LlmFallbackPlan(
                commands=[LlmShellCommand(command=["python", "-V"])],
                file_writes=[LlmFileWrite(file_path=str(target), content="print('ok')\n")],
                notes="apply fix",
            )

            result = executor.execute_plan(plan)

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(target.exists())
            self.assertIn(["python", "-V"], engine.commands)

    def test_allows_file_writes_only(self) -> None:
        engine = FakeExecutionEngine()
        executor = UnrestrictedLlmFallbackExecutor(engine)

        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "only_write.py"
            plan = LlmFallbackPlan(file_writes=[LlmFileWrite(file_path=str(target), content="x=1\n")])

            result = executor.execute_plan(plan)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.command, ["internal", "llm_fallback", "file_writes_only"])
            self.assertEqual(target.read_text(encoding="utf-8"), "x=1\n")

    def test_blocks_non_whitelisted_llm_command(self) -> None:
        engine = FakeExecutionEngine()
        executor = UnrestrictedLlmFallbackExecutor(engine)
        plan = LlmFallbackPlan(commands=[LlmShellCommand(command=["curl", "http://example.com"])])

        result = executor.execute_plan(plan)

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Guardrails blocked LLM command", result.stderr)
        self.assertEqual(engine.commands, [])


if __name__ == "__main__":
    unittest.main()
