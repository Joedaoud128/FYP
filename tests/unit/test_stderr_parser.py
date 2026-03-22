from __future__ import annotations

import sys
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.domain.models import ExecutionResult
from phase4.parsing.stderr_parser import PythonStderrParser


class TestPythonStderrParser(unittest.TestCase):
    def test_parse_module_not_found_error(self) -> None:
        parser = PythonStderrParser()
        result = ExecutionResult(
            command=["python", "-c", "import yfinance"],
            exit_code=1,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                "  File \"<string>\", line 1, in <module>\n"
                "ModuleNotFoundError: No module named 'yfinance'\n"
            ),
        )

        record = parser.parse(result)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.exception_name, "ModuleNotFoundError")
        self.assertEqual(record.module_name, "yfinance")

    def test_parse_syntax_error_file_and_line(self) -> None:
        parser = PythonStderrParser()
        result = ExecutionResult(
            command=["python", "bad.py"],
            exit_code=1,
            stdout="",
            stderr=(
                '  File "bad.py", line 7\n'
                "    if True\n"
                "           ^\n"
                "SyntaxError: expected ':'\n"
            ),
        )

        record = parser.parse(result)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.exception_name, "SyntaxError")
        self.assertEqual(record.source_file, "bad.py")
        self.assertEqual(record.line_number, 7)

    def test_parse_file_not_found_missing_path(self) -> None:
        parser = PythonStderrParser()
        result = ExecutionResult(
            command=["python", "app.py"],
            exit_code=1,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                '  File "app.py", line 3, in <module>\n'
                "    open('data/input.txt')\n"
                "FileNotFoundError: [Errno 2] No such file or directory: 'data/input.txt'\n"
            ),
        )

        record = parser.parse(result)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record.exception_name, "FileNotFoundError")
        self.assertEqual(record.missing_path, "data/input.txt")


if __name__ == "__main__":
    unittest.main()
