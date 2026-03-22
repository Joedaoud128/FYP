from __future__ import annotations

import hashlib
import json

from phase4.domain.models import ClassificationResult, CorrectiveAction, ErrorRecord


def build_error_fingerprint(error: ErrorRecord, classification: ClassificationResult) -> str:
    payload = {
        "rule_id": classification.rule_id.value,
        "exception_name": error.exception_name,
        "message": _normalize_message(error.message),
        "source_file": error.source_file,
        "line_number": error.line_number,
        "module_name": error.module_name,
        "missing_path": error.missing_path,
    }
    return _stable_hash(payload)


def build_action_fingerprint(action: CorrectiveAction) -> str:
    payload = {
        "action_type": action.action_type.value,
        "command": action.command or [],
        "arguments": action.arguments,
    }
    return _stable_hash(payload)


def _stable_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_message(message: str) -> str:
    return " ".join(message.strip().split())
