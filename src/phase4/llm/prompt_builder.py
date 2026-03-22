from __future__ import annotations

import json

from phase4.domain.models import ClassificationResult, ErrorRecord, ExecutionResult


def build_llm_prompt(
    command: list[str],
    execution_result: ExecutionResult,
    parsed_error: ErrorRecord | None,
    classification: ClassificationResult | None,
) -> str:
    context = {
        "command": command,
        "exit_code": execution_result.exit_code,
        "stderr": execution_result.stderr,
        "stdout": execution_result.stdout,
        "parsed_error": None
        if parsed_error is None
        else {
            "exception_name": parsed_error.exception_name,
            "message": parsed_error.message,
            "source_file": parsed_error.source_file,
            "line_number": parsed_error.line_number,
            "module_name": parsed_error.module_name,
            "missing_path": parsed_error.missing_path,
        },
        "classification": None
        if classification is None
        else {
            "rule_id": classification.rule_id.value,
            "error_type": classification.error_type.value,
            "confidence": classification.confidence,
            "reason": classification.reason,
        },
    }

    schema = {
        "proposal_type": "script_patch|command",
        "rationale": "string",
        "target_file": "relative/or/absolute/path.py (required for script_patch)",
        "script_content": "full python file content (required for script_patch)",
        "command": ["token1", "token2"],
    }

    return (
        "You are a local remediation assistant. Return ONLY JSON.\n"
        "Prefer deterministic-safe fixes.\n"
        "If providing command, keep it minimal and safe.\n"
        f"Required JSON schema: {json.dumps(schema)}\n"
        f"Runtime context: {json.dumps(context)}"
    )
