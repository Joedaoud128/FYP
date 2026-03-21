from __future__ import annotations

import subprocess

from phase4.domain.models import ExecutionResult


class SubprocessExecutionEngine:
    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ExecutionResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
