from __future__ import annotations

from pathlib import Path

from phase4.domain.interfaces import ConfidenceGate
from phase4.domain.models import ClassificationResult, Phase4PolicyConfig, PolicyDecision, RuleId


def default_policy_config(workspace_root: str | None = None) -> Phase4PolicyConfig:
    root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
    return Phase4PolicyConfig(
        rule_thresholds={
            RuleId.MODULE_NOT_FOUND: 0.9,
            RuleId.IMPORT_NO_MODULE: 0.9,
            RuleId.SYNTAX_ERROR: 0.95,
            RuleId.INDENTATION_ERROR: 0.95,
            RuleId.FILE_NOT_FOUND: 1.1,
            RuleId.OTHER: 1.1,
        },
        default_threshold=0.95,
        file_creation_allowlist=(),
        journal_path=root / ".phase4" / "action_journal.jsonl",
    )


class ThresholdConfidenceGate(ConfidenceGate):
    def __init__(self, policy: Phase4PolicyConfig) -> None:
        self._policy = policy

    def evaluate(self, classification: ClassificationResult) -> PolicyDecision:
        threshold = self._policy.rule_thresholds.get(classification.rule_id, self._policy.default_threshold)
        return PolicyDecision.ALLOW if classification.confidence >= threshold else PolicyDecision.DENY
