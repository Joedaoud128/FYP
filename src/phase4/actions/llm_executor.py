from __future__ import annotations

from pathlib import Path

from phase4.domain.interfaces import ExecutionEngine
from phase4.domain.models import ExecutionResult, LlmFallbackPlan


class UnrestrictedLlmFallbackExecutor:
    def __init__(self, execution_engine: ExecutionEngine, timeout_seconds: int = 300) -> None:
        self._execution_engine = execution_engine
        self._timeout_seconds = timeout_seconds

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
            last_result = self._execution_engine.run(command.command, timeout_seconds=self._timeout_seconds)
            if last_result.exit_code != 0:
                return last_result
        return last_result
