from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.actions.planner import DeterministicActionPlanner
from phase4.classifier.deterministic import DeterministicPythonErrorClassifier
from phase4.domain.models import ActionType, ErrorRecord, ErrorType


class TestClassifierAndPlanner(unittest.TestCase):
    def test_module_not_found_maps_to_pip_install(self) -> None:
        classifier = DeterministicPythonErrorClassifier()
        planner = DeterministicActionPlanner("python")

        error = ErrorRecord(
            exception_name="ModuleNotFoundError",
            message="No module named 'yfinance'",
            raw_stderr="ModuleNotFoundError: No module named 'yfinance'",
            module_name="yfinance",
        )

        classification = classifier.classify(error)
        action = planner.plan(classification)

        self.assertEqual(classification.error_type, ErrorType.MODULE_NOT_FOUND)
        self.assertIsNotNone(action)
        assert action is not None
        self.assertEqual(action.command, ["python", "-m", "pip", "install", "yfinance"])

    def test_indentation_error_maps_to_normalize_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_file = Path(tmp_dir) / "src" / "bad.py"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("\tprint('x')\n", encoding="utf-8")

            classifier = DeterministicPythonErrorClassifier()
            planner = DeterministicActionPlanner("python", workspace_root=tmp_dir)

            error = ErrorRecord(
                exception_name="IndentationError",
                message="unexpected indent",
                raw_stderr="IndentationError: unexpected indent",
                source_file=str(source_file),
                line_number=1,
            )

            classification = classifier.classify(error)
            action = planner.plan(classification)

            self.assertEqual(classification.error_type, ErrorType.INDENTATION_ERROR)
            self.assertIsNotNone(action)
            assert action is not None
            self.assertEqual(action.action_type, ActionType.NORMALIZE_INDENTATION)
            self.assertEqual(action.arguments["line_number"], 1)

    def test_file_not_found_is_denied_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            classifier = DeterministicPythonErrorClassifier()
            planner = DeterministicActionPlanner("python", workspace_root=tmp_dir)

            error = ErrorRecord(
                exception_name="FileNotFoundError",
                message="[Errno 2] No such file or directory: 'data/input.txt'",
                raw_stderr="FileNotFoundError: [Errno 2] No such file or directory: 'data/input.txt'",
                missing_path="data/input.txt",
            )

            classification = classifier.classify(error)
            action = planner.plan(classification)

            self.assertEqual(classification.error_type, ErrorType.FILE_NOT_FOUND)
            self.assertIsNone(action)

    def test_file_not_found_maps_to_create_when_allowlisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            classifier = DeterministicPythonErrorClassifier()
            planner = DeterministicActionPlanner(
                "python",
                workspace_root=tmp_dir,
                file_creation_allowlist=("data",),
            )

            error = ErrorRecord(
                exception_name="FileNotFoundError",
                message="[Errno 2] No such file or directory: 'data/input.txt'",
                raw_stderr="FileNotFoundError: [Errno 2] No such file or directory: 'data/input.txt'",
                missing_path="data/input.txt",
            )

            classification = classifier.classify(error)
            action = planner.plan(classification)

            self.assertIsNotNone(action)
            assert action is not None
            self.assertEqual(action.action_type, ActionType.CREATE_MISSING_FILE)


if __name__ == "__main__":
    unittest.main()
