from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.domain.models import (
    ActionStatus,
    ClassificationResult,
    ErrorType,
    JournalRecord,
    PolicyDecision,
    RuleId,
)
from phase4.runtime.jsonl_journal import JsonlActionJournal
from phase4.workflow.policy import ThresholdConfidenceGate, default_policy_config


class TestPolicyAndJournal(unittest.TestCase):
    def test_threshold_confidence_gate(self) -> None:
        policy = default_policy_config()
        gate = ThresholdConfidenceGate(policy)

        classification = ClassificationResult(
            rule_id=RuleId.MODULE_NOT_FOUND,
            error_type=ErrorType.MODULE_NOT_FOUND,
            module_name="yfinance",
            source_file=None,
            line_number=None,
            missing_path=None,
            diagnostic_message="No module named 'yfinance'",
            confidence=0.95,
            reason="test",
        )

        decision = gate.evaluate(classification)
        self.assertEqual(decision, PolicyDecision.ALLOW)

    def test_jsonl_journal_persists_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "journal.jsonl"
            journal = JsonlActionJournal(str(path))

            journal.record(
                JournalRecord(
                    timestamp_utc="2026-03-06T00:00:00+00:00",
                    attempt=1,
                    error_fingerprint="e1",
                    action_fingerprint="a1",
                    rule_id=RuleId.MODULE_NOT_FOUND.value,
                    confidence=1.0,
                    policy_decision=PolicyDecision.ALLOW.value,
                    action_type="pip_install",
                    action_status=ActionStatus.EXECUTED,
                    execution_exit_code=1,
                    action_exit_code=0,
                    message="ok",
                )
            )

            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["attempt"], 1)
            self.assertEqual(payload["action_status"], "executed")


if __name__ == "__main__":
    unittest.main()
