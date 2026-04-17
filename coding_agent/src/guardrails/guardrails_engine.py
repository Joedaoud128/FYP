"""
AI Coding Agent — Module 7: Policy Check (Guardrails Engine)
=============================================================

This module loads guardrails_config.yaml and exposes a single function:

    validate(request: dict) -> dict

Both the Code Generation service and the Code Debugging service call
this function through the shared pipeline:

    Tool Selector (Module 6) → Policy Check (Module 7) → Action Executor (Module 8)

The module is stateless after initialization. It reads the YAML once
at import time and validates every command against it identically,
regardless of which service is the caller.

Usage:
    from guardrails_engine import GuardrailsEngine

    engine = GuardrailsEngine("guardrails_config.yaml")
    response = engine.validate({
        "caller_service": "generation",        # or "debugging"
        "raw_command":    "python main.py",
        "working_dir":    "/workspace/my_project"
    })

    if response["status"] == "PASS":
        # Forward response["token_array"] to Action Executor
        ...
    else:
        # Feed response["reason"] and response["failing_rule_id"]
        # back to Reasoning Engine (Module 4)
        ...
"""

import os
import re
import shlex
import logging
import datetime
from pathlib import Path
from typing import Any

import yaml


# ── Logging setup ──────────────────────────────────────────────────────────
logger = logging.getLogger("guardrails")


# ── Custom exceptions ──────────────────────────────────────────────────────
class GuardrailReject(Exception):
    """Raised when a command violates a whitelist or positional rule."""

    def __init__(self, reason: str, failing_rule_id: str):
        self.reason = reason
        self.failing_rule_id = failing_rule_id
        super().__init__(reason)


class GuardrailBlock(Exception):
    """Raised when a command contains variable expansion or metacharacters
    that make it non-deterministic and therefore unconditionally blocked."""

    def __init__(self, reason: str, matched_expansion: str):
        self.reason = reason
        self.matched_expansion = matched_expansion
        super().__init__(reason)


# ── Path validator ─────────────────────────────────────────────────────────
class PathValidator:
    """Implements the three path validation rules from the YAML:
    PATH-01  workspace confinement
    PATH-02  ../ traversal blocking
    PATH-03  symlink escape prevention
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = os.path.realpath(workspace_root)

    def validate(self, raw_path: str, working_dir: str) -> None:
        """Validate a single path operand. Raises GuardrailReject on failure."""

        # Resolve relative paths against the working directory
        if not os.path.isabs(raw_path):
            full_path = os.path.join(working_dir, raw_path)
        else:
            full_path = raw_path

        # PATH-02: Block ../ traversal (check raw string before resolution)
        if "../" in raw_path or "..\\" in raw_path:
            raise GuardrailReject(
                f"Path contains directory traversal: '{raw_path}'",
                "PATH-02",
            )

        # PATH-01 + PATH-03: Resolve symlinks, then check confinement
        resolved = os.path.realpath(full_path)
        if not (resolved == self.workspace_root or resolved.startswith(self.workspace_root + os.sep)):
            raise GuardrailReject(
                f"Path resolves outside workspace: '{raw_path}' -> '{resolved}'",
                "PATH-01",
            )


# ── Operand validators ─────────────────────────────────────────────────────
# Regex for valid PyPI package names
_PACKAGE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _validate_operand(
    token: str,
    expected: str,
    constraint: str | None,
    allowed: list[str] | None,
    position: int,
    path_validator: PathValidator,
    working_dir: str,
) -> None:
    """Validate a single operand token based on its expected type and constraint.
    Raises GuardrailReject on failure."""

    if expected == "filepath":
        # Must end with .py if the constraint says so
        if constraint and "must end with .py" in constraint:
            if not token.endswith(".py"):
                raise GuardrailReject(
                    f"${position} must be a .py file, got '{token}'",
                    f"operand_constraint_pos_{position}",
                )
        # Must resolve inside workspace
        path_validator.validate(token, working_dir)

    elif expected == "dirpath":
        path_validator.validate(token, working_dir)

    elif expected == "integer":
        if not token.lstrip("-").isdigit():
            raise GuardrailReject(
                f"${position} must be an integer, got '{token}'",
                f"operand_constraint_pos_{position}",
            )
        value = int(token)
        # Parse constraint bounds if present  (e.g. "1 <= value <= 4")
        if constraint:
            bound_match = re.match(
                r"(\d+)\s*<=\s*value\s*<=\s*(\d+)", constraint
            )
            if bound_match:
                lo, hi = int(bound_match.group(1)), int(bound_match.group(2))
                if not (lo <= value <= hi):
                    raise GuardrailReject(
                        f"${position} integer {value} out of bounds "
                        f"({lo}..{hi})",
                        f"operand_constraint_pos_{position}",
                    )
            elif "positive" in constraint and value <= 0:
                raise GuardrailReject(
                    f"${position} must be a positive integer, got {value}",
                    f"operand_constraint_pos_{position}",
                )

    elif expected == "package_name":
        if not _PACKAGE_NAME_RE.match(token):
            raise GuardrailReject(
                f"${position} is not a valid package name: '{token}'",
                f"operand_constraint_pos_{position}",
            )

    elif expected == "pattern":
        # Pattern must not contain shell metacharacters
        # (uses the same blocked_shell_patterns from global config,
        #  but the raw-string scan in Step 1 already catches most of these.
        #  This is a second line of defense at the operand level.)
        for ch in [";", "|", "&&", ">", ">>", "`", "$(", "${"]:
            if ch in token:
                raise GuardrailReject(
                    f"${position} pattern contains shell metacharacter: '{ch}'",
                    f"operand_constraint_pos_{position}",
                )

    elif expected == "string":
        # Must be one of the explicitly allowed values
        if allowed and token not in allowed:
            raise GuardrailReject(
                f"${position} must be one of {allowed}, got '{token}'",
                f"operand_constraint_pos_{position}",
            )


# ── Template matcher ───────────────────────────────────────────────────────
def _match_template(
    tokens: list[str],
    command_def: dict,
    path_validator: PathValidator,
    working_dir: str,
) -> None:
    """Walk the token array against the command's token_order_template.
    Raises GuardrailReject if any position fails.

    Handles optional positions: if a template position is marked optional
    and the current token does not match, the matcher skips that template
    slot and retries the same token against the next slot.
    """
    template = command_def["token_order_template"]
    max_tokens = command_def.get("max_tokens", len(template))
    blocked_flags = command_def.get("blocked_flags", [])
    blocked_predicates = command_def.get("blocked_predicates", [])

    # ── Step 6: extra tokens ──
    if len(tokens) > max_tokens:
        raise GuardrailReject(
            f"Too many tokens: expected at most {max_tokens}, "
            f"got {len(tokens)}",
            "token_order_step_6",
        )

    # ── Check for blocked flags / predicates anywhere in the command ──
    for tok in tokens[1:]:
        if tok in blocked_flags:
            raise GuardrailReject(
                f"Blocked flag '{tok}' detected",
                "blocked_flag",
            )
        if tok in blocked_predicates:
            raise GuardrailReject(
                f"Blocked predicate '{tok}' detected",
                "blocked_predicate",
            )

    # ── Positional walk ──
    tok_idx = 1  # skip $0 (already matched by the caller)
    tmpl_idx = 1  # skip position 0 in template

    while tmpl_idx < len(template) and tok_idx < len(tokens):
        slot = template[tmpl_idx]
        token = tokens[tok_idx]
        slot_type = slot["type"]
        is_optional = slot.get("optional", False)

        if slot_type in ("flag", "subcommand"):
            allowed_values = slot.get("allowed", [])
            if slot_type == "flag" and "value" in slot:
                allowed_values = [slot["value"]]

            if token in allowed_values:
                tok_idx += 1
                tmpl_idx += 1
            elif is_optional:
                # Skip this optional slot; don't consume the token
                tmpl_idx += 1
            else:
                raise GuardrailReject(
                    f"${tok_idx} must be one of {allowed_values}, "
                    f"got '{token}'",
                    "token_order_step_5",
                )

        elif slot_type == "executable":
            # Position 0 is handled before this function; shouldn't appear again
            tmpl_idx += 1

        elif slot_type == "operand":
            _validate_operand(
                token=token,
                expected=slot.get("expected", "string"),
                constraint=slot.get("constraint"),
                allowed=slot.get("allowed"),
                position=tok_idx,
                path_validator=path_validator,
                working_dir=working_dir,
            )
            tok_idx += 1
            tmpl_idx += 1
        else:
            raise GuardrailReject(
                f"Unknown slot type '{slot_type}' in template at "
                f"position {tmpl_idx}",
                "template_error",
            )

    # If there are unconsumed tokens, reject
    if tok_idx < len(tokens):
        raise GuardrailReject(
            f"Unexpected extra tokens starting at ${tok_idx}: "
            f"'{tokens[tok_idx]}'",
            "token_order_step_6",
        )

    # If there are remaining required template slots, reject
    while tmpl_idx < len(template):
        if not template[tmpl_idx].get("optional", False):
            raise GuardrailReject(
                f"Missing required token at position {tmpl_idx} "
                f"(expected {template[tmpl_idx].get('type')})",
                "token_order_step_5",
            )
        tmpl_idx += 1


# ── Main engine ────────────────────────────────────────────────────────────
class GuardrailsEngine:
    """Loads guardrails_config.yaml and validates commands against it.

    This is Module 7 (Policy Check) of the AI Coding Agent architecture.
    """

    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

        g = self._config["global"]
        # Allow runtime override via AGENT_WORKSPACE so the same YAML works
        # in Docker (/workspace), on Linux dev machines, and in CI without
        # editing the config file. Falls back to the YAML value if not set.
        self._workspace_root: str = os.environ.get(
            "AGENT_WORKSPACE",
            g["workspace_root"]
        ) or g["workspace_root"]
        self._blocked_patterns = g["blocked_shell_patterns"]
        self._blocked_expansions = g["blocked_variable_expansions"]
        self._resource_limits = g["resource_limits"]

        self._commands = self._config["commands"]
        self._log_config = self._config.get("logging", {})

        self._path_validator = PathValidator(self._workspace_root)

        # Build a lookup: executable name → list of (command_key, command_def)
        # Multiple command keys can share the same executable (e.g. "python").
        self._exe_index: dict[str, list[tuple[str, dict]]] = {}
        for key, cmd_def in self._commands.items():
            exe = cmd_def["executable"]
            self._exe_index.setdefault(exe, []).append((key, cmd_def))

    # ── Public properties ──────────────────────────────────────────────────

    @property
    def workspace_root(self) -> str:
        return self._workspace_root

    @property
    def resource_limits(self) -> dict:
        return dict(self._resource_limits)

    # ── The core validate function ─────────────────────────────────────────

    def validate(self, request: dict) -> dict:
        """Validate a command against the guardrails configuration.

        Args:
            request: {
                "caller_service": "generation" | "debugging",
                "raw_command":    str,
                "working_dir":    str
            }

        Returns:
            {
                "status":          "PASS" | "REJECT" | "BLOCK",
                "command_key":     str | None,
                "token_array":     list[str],
                "reason":          str | None,
                "failing_rule_id": str | None
            }
        """
        caller = request.get("caller_service", "unknown")
        raw_command = request["raw_command"]
        working_dir = request.get("working_dir", self._workspace_root)
        token_array: list[str] = []

        try:
            # ── Step 1: Scan for blocked shell metacharacters ──────────
            # Sort by length descending so ">>" is checked before ">"
            sorted_patterns = sorted(
                self._blocked_patterns, key=len, reverse=True
            )
            for pattern in sorted_patterns:
                if pattern in raw_command:
                    raise GuardrailReject(
                        f"Shell metacharacter detected: '{pattern}'",
                        "token_order_step_1",
                    )

            # ── Step 2: Scan for blocked variable expansions ───────────
            for expansion in self._blocked_expansions:
                if expansion in raw_command:
                    raise GuardrailBlock(
                        f"Variable expansion detected: '{expansion}'",
                        expansion,
                    )

            # ── Step 3: Tokenize ───────────────────────────────────────
            try:
                token_array = shlex.split(raw_command)
            except ValueError as e:
                raise GuardrailReject(
                    f"Tokenization failed: {e}",
                    "token_order_step_3",
                )

            if not token_array:
                raise GuardrailReject(
                    "Empty command after tokenization",
                    "token_order_step_3",
                )

            # ── Step 4: Match $0 against the whitelist ─────────────────
            executable = token_array[0]
            candidates = self._exe_index.get(executable)
            if candidates is None:
                raise GuardrailReject(
                    f"Executable '{executable}' is not whitelisted",
                    "token_order_step_4",
                )

            # ── Step 5–7: Try each candidate template for this exe ─────
            # Multiple commands can share the same executable (e.g. python).
            # We try each candidate template. If one matches fully, PASS.
            # If none match, we report the error from the best candidate.
            last_error: GuardrailReject | None = None
            matched_key: str | None = None

            for cmd_key, cmd_def in candidates:
                try:
                    _match_template(
                        tokens=token_array,
                        command_def=cmd_def,
                        path_validator=self._path_validator,
                        working_dir=working_dir,
                    )
                    matched_key = cmd_key
                    break
                except GuardrailReject as e:
                    last_error = e
                    continue

            if matched_key is None:
                # None of the templates matched
                if last_error is not None:
                    raise last_error
                raise GuardrailReject(
                    f"No matching template for '{executable}' command",
                    "token_order_step_5",
                )

            # ── PASS ──
            self._log_event("on_pass", {
                "caller_service": caller,
                "command_key": matched_key,
                "token_array": token_array,
            })

            return {
                "status": "PASS",
                "command_key": matched_key,
                "token_array": token_array,
                "reason": None,
                "failing_rule_id": None,
            }

        except GuardrailReject as e:
            self._log_event("on_reject", {
                "caller_service": caller,
                "raw_command": raw_command,
                "token_array": token_array,
                "failing_rule_id": e.failing_rule_id,
                "reason": e.reason,
            })
            return {
                "status": "REJECT",
                "command_key": None,
                "token_array": token_array,
                "reason": e.reason,
                "failing_rule_id": e.failing_rule_id,
            }

        except GuardrailBlock as e:
            self._log_event("on_block", {
                "caller_service": caller,
                "raw_command": raw_command,
                "matched_expansion": e.matched_expansion,
                "reason": e.reason,
            })
            return {
                "status": "BLOCK",
                "command_key": None,
                "token_array": token_array,
                "reason": e.reason,
                "failing_rule_id": "token_order_step_2",
            }

    # ── Logging helper ─────────────────────────────────────────────────────

    def _log_event(self, event_type: str, data: dict) -> None:
        """Emit a structured log entry based on the logging section of the
        YAML config."""
        log_conf = self._log_config.get(event_type)
        if log_conf is None:
            return

        level_str = log_conf.get("log_level", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)

        entry = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        for field in log_conf.get("fields", []):
            if field == "timestamp":
                continue
            if field in data:
                entry[field] = data[field]

        logger.log(level, "%s: %s", event_type, entry)