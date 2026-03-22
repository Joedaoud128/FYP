from __future__ import annotations

import json

from phase4.domain.models import LlmProposal, LlmProposalType


def parse_llm_proposal(raw_text: str) -> LlmProposal | None:
    payload = _extract_json(raw_text)
    if payload is None:
        return None

    proposal_type = payload.get("proposal_type")
    rationale = payload.get("rationale", "")

    if proposal_type == LlmProposalType.SCRIPT_PATCH.value:
        target_file = payload.get("target_file")
        script_content = payload.get("script_content")
        if not isinstance(target_file, str) or not isinstance(script_content, str):
            return None
        return LlmProposal(
            proposal_type=LlmProposalType.SCRIPT_PATCH,
            rationale=rationale,
            target_file=target_file,
            script_content=script_content,
        )

    if proposal_type == LlmProposalType.COMMAND.value:
        command = payload.get("command")
        if not isinstance(command, list) or not all(isinstance(token, str) for token in command):
            return None
        return LlmProposal(
            proposal_type=LlmProposalType.COMMAND,
            rationale=rationale,
            command=command,
        )

    return None


def _extract_json(raw_text: str) -> dict[str, object] | None:
    raw_text = raw_text.strip()
    if not raw_text:
        return None

    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw_text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
