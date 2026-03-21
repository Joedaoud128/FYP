from __future__ import annotations

import re

from phase4.domain.models import ErrorRecord, ExecutionResult


class PythonStderrParser:
    _NO_MODULE_PATTERN = re.compile(r"No module named ['\"]([a-zA-Z0-9_.-]+)['\"]")
    _EXCEPTION_PATTERN = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*Error):\s*(?P<message>.+)")
    _TRACEBACK_FILE_LINE_PATTERN = re.compile(r"File ['\"](?P<file>[^'\"]+)['\"], line (?P<line>\d+)")
    _MISSING_FILE_PATTERN = re.compile(r"No such file or directory:\s*['\"](?P<path>[^'\"]+)['\"]")

    def parse(self, execution_result: ExecutionResult) -> ErrorRecord | None:
        stderr = execution_result.stderr.strip()
        if not stderr:
            return None

        exception_name = "UnknownError"
        message = stderr.splitlines()[-1] if stderr.splitlines() else stderr

        for line in reversed(stderr.splitlines()):
            match = self._EXCEPTION_PATTERN.search(line.strip())
            if match:
                exception_name = match.group("name")
                message = match.group("message")
                break

        module_name = self._extract_module_name(stderr)
        source_file, line_number = self._extract_source_context(stderr)
        missing_path = self._extract_missing_path(stderr)
        return ErrorRecord(
            exception_name=exception_name,
            message=message,
            raw_stderr=stderr,
            module_name=module_name,
            source_file=source_file,
            line_number=line_number,
            missing_path=missing_path,
        )

    def _extract_module_name(self, stderr: str) -> str | None:
        match = self._NO_MODULE_PATTERN.search(stderr)
        if not match:
            return None
        full_name = match.group(1)
        return full_name.split(".")[0]

    def _extract_source_context(self, stderr: str) -> tuple[str | None, int | None]:
        matches = list(self._TRACEBACK_FILE_LINE_PATTERN.finditer(stderr))
        if not matches:
            return None, None
        last_match = matches[-1]
        return last_match.group("file"), int(last_match.group("line"))

    def _extract_missing_path(self, stderr: str) -> str | None:
        match = self._MISSING_FILE_PATTERN.search(stderr)
        if match is None:
            return None
        return match.group("path")
