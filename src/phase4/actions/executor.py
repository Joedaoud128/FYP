from __future__ import annotations

from pathlib import Path
import sys

from phase4.domain.interfaces import ExecutionEngine
from phase4.domain.models import ActionType, CorrectiveAction, ExecutionResult


class GuardedActionExecutor:
    def __init__(
        self,
        execution_engine: ExecutionEngine,
        timeout_seconds: int = 300,
        python_executable: str | None = None,
    ) -> None:
        self._execution_engine = execution_engine
        self._timeout_seconds = timeout_seconds
        self._python_executable = python_executable or sys.executable

    def execute(self, action: CorrectiveAction) -> ExecutionResult:
        if not action.safe_to_auto_execute:
            raise ValueError("Refusing to execute unsafe corrective action.")

        if action.action_type == ActionType.PIP_INSTALL:
            if action.command is None:
                raise ValueError("PIP_INSTALL action requires a command.")
            return self._execution_engine.run(action.command, timeout_seconds=self._timeout_seconds)

        if action.action_type == ActionType.NORMALIZE_INDENTATION:
            return self._normalize_indentation(action)

        if action.action_type == ActionType.CREATE_MISSING_FILE:
            return self._create_missing_file(action)

        return ExecutionResult(
            command=["internal", "unsupported_action", action.action_type.value],
            exit_code=1,
            stdout="",
            stderr=f"Unsupported deterministic action: {action.action_type.value}",
        )

    def _normalize_indentation(self, action: CorrectiveAction) -> ExecutionResult:
        file_path = action.arguments.get("file_path")
        line_number = action.arguments.get("line_number")
        if not isinstance(file_path, str) or not isinstance(line_number, int):
            return ExecutionResult(
                command=["internal", "normalize_indentation"],
                exit_code=1,
                stdout="",
                stderr="Invalid action arguments for indentation normalization.",
            )

        target = Path(file_path)
        if not target.exists() or not target.is_file():
            return ExecutionResult(
                command=["internal", "normalize_indentation", file_path],
                exit_code=1,
                stdout="",
                stderr=f"Source file does not exist: {file_path}",
            )

        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        original_content = "".join(lines)
        index = line_number - 1
        if index < 0 or index >= len(lines):
            return ExecutionResult(
                command=["internal", "normalize_indentation", file_path, str(line_number)],
                exit_code=1,
                stdout="",
                stderr=f"Line number {line_number} is out of range for {file_path}.",
            )

        original_line = lines[index]
        newline_suffix = "\n" if original_line.endswith("\n") else ""
        content = original_line[:-1] if newline_suffix else original_line
        leading_len = len(content) - len(content.lstrip(" \t"))
        leading = content[:leading_len].replace("\t", "    ")
        normalized_line = f"{leading}{content[leading_len:].rstrip()}{newline_suffix}"
        lines[index] = normalized_line

        target.write_text("".join(lines), encoding="utf-8")

        compile_result = self._execution_engine.run(
            [self._python_executable, "-m", "py_compile", str(target)],
            timeout_seconds=self._timeout_seconds,
        )
        if compile_result.exit_code != 0:
            target.write_text(original_content, encoding="utf-8")
            return ExecutionResult(
                command=["internal", "normalize_indentation", file_path, str(line_number)],
                exit_code=1,
                stdout="",
                stderr=f"Validation failed after indentation normalization. Rolled back changes. {compile_result.stderr.strip()}",
            )

        return ExecutionResult(
            command=["internal", "normalize_indentation", file_path, str(line_number)],
            exit_code=0,
            stdout=f"Normalized indentation in {file_path}:{line_number}",
            stderr="",
        )

    def _create_missing_file(self, action: CorrectiveAction) -> ExecutionResult:
        file_path = action.arguments.get("file_path")
        if not isinstance(file_path, str):
            return ExecutionResult(
                command=["internal", "create_missing_file"],
                exit_code=1,
                stdout="",
                stderr="Invalid action arguments for missing file creation.",
            )

        target = Path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.is_file():
            return ExecutionResult(
                command=["internal", "create_missing_file", file_path],
                exit_code=1,
                stdout="",
                stderr=f"File already exists and creation was skipped: {file_path}",
            )

        target.write_text("", encoding="utf-8")

        return ExecutionResult(
            command=["internal", "create_missing_file", file_path],
            exit_code=0,
            stdout=f"Ensured file exists: {file_path}",
            stderr="",
        )
