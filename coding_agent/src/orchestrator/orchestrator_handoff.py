"""
orchestrator_handoff.py
=======================
Orchestrator Module 11 - Handoff Validation & Environment Preparation

This module implements the data handoff between the Code Generation
module (Joe) and the Code Debugging module (Raymond). It contains
two classes:

    1. HandoffValidator  - Validates Schema A (generation_output)
    2. EnvironmentPreparer - Transforms Schema A into Schema B
                             (execution_context)

Standard: JSON RFC 8259 (all inter-module communication)
Security: Aligned with Policy Check (Module 7) path validation rules
Author:   Maria (Orchestrator)
"""

import os
import sys
import re
import json
import shutil
import logging
from datetime import datetime
from typing import Any


def _detect_system_python() -> str:
    """
    Always return the exact Python executable that launched this process.
    This guarantees the same interpreter is used for subprocess execution,
    which is critical on Windows where 'python3' may not be in PATH.
    """
    return sys.executable


SYSTEM_PYTHON = _detect_system_python()


# ──────────────────────────────────────────────
# Custom Exceptions
# ──────────────────────────────────────────────

class HandoffValidationError(Exception):
    """Base exception for all handoff validation failures."""
    pass


class MissingFieldError(HandoffValidationError):
    """Raised when required fields are absent from the payload."""
    pass


class GenerationFailedError(HandoffValidationError):
    """Raised when generation_status is not 'success'."""
    pass


class FileValidationError(HandoffValidationError):
    """Raised when a referenced file or directory does not exist."""
    pass


class PathSecurityError(HandoffValidationError):
    """Raised when a path violates workspace confinement rules."""
    pass


# ──────────────────────────────────────────────
# HandoffValidator (Schema A validation)
# ──────────────────────────────────────────────

class HandoffValidator:
    """
    Validates the generation_output payload (Schema A) before
    the Orchestrator transforms it and passes it to the
    Code Debugging module.

    Validation checks (V1-V7) are defined in the Handoff Schema
    Specification document, Section 6.

    Usage:
        validator = HandoffValidator()
        validated_payload = validator.validate(generation_output)
    """

    # V1: Required top-level fields in Schema A
    REQUIRED_FIELDS = [
        "task_id",
        "generated_script",
        "requirements",
        "workspace_dir",
        "venv_created",
        "generation_status",
        "metadata",
    ]

    # V1: Required fields inside the metadata sub-object
    REQUIRED_METADATA_FIELDS = [
        "complexity",
        "domain",
        "estimated_libraries",
        "generation_timestamp",
    ]

    def __init__(self):
        self.logger = logging.getLogger("orchestrator.validator")

    def validate(self, payload: dict) -> dict:
        """
        Run all validation checks (V1-V7) on the generation_output
        payload. Returns the validated payload if all checks pass.
        Raises a specific exception if any check fails.

        Args:
            payload: The generation_output JSON from Joe's module.

        Returns:
            The same payload, confirmed valid.

        Raises:
            MissingFieldError: V1 - required fields are missing.
            GenerationFailedError: V2 - generation did not succeed.
            FileValidationError: V3/V4/V6 - files or dirs not found.
            PathSecurityError: V5 - path traversal detected.
        """
        self.logger.info(
            "Starting handoff validation for task: %s",
            payload.get("task_id", "UNKNOWN")
        )

        self._check_required_fields(payload)       # V1
        self._check_generation_status(payload)      # V2
        self._check_script_exists(payload)          # V3
        self._check_workspace_exists(payload)       # V4
        self._check_path_security(payload)          # V5
        self._check_venv_if_created(payload)        # V6
        self._check_requirements_consistency(payload)  # V7
        self._check_interactive_input(payload)      # V8

        self.logger.info(
            "Handoff validation PASSED for task: %s",
            payload["task_id"]
        )
        return payload

    # ── V1: Required fields present ──

    def _check_required_fields(self, payload: dict) -> None:
        """V1: Verify all required fields exist in the payload."""
        missing = [
            f for f in self.REQUIRED_FIELDS
            if f not in payload
        ]
        if missing:
            msg = f"Missing required fields: {missing}"
            self.logger.error("V1 FAILED - %s", msg)
            raise MissingFieldError(msg)

        # Also check metadata sub-fields
        metadata = payload.get("metadata", {})
        missing_meta = [
            f for f in self.REQUIRED_METADATA_FIELDS
            if f not in metadata
        ]
        if missing_meta:
            msg = f"Missing metadata fields: {missing_meta}"
            self.logger.error("V1 FAILED - %s", msg)
            raise MissingFieldError(msg)

        self.logger.debug("V1 PASSED - All required fields present")

    # ── V2: Generation status is "success" ──

    def _check_generation_status(self, payload: dict) -> None:
        """V2: Verify generation completed successfully."""
        status = payload["generation_status"]
        if status != "success":
            msg = (
                f"Generation status is '{status}', "
                f"expected 'success'. Pipeline halted."
            )
            self.logger.error("V2 FAILED - %s", msg)
            raise GenerationFailedError(msg)

        self.logger.debug("V2 PASSED - Generation status is 'success'")

    # ── V3: Script file exists on disk ──

    def _check_script_exists(self, payload: dict) -> None:
        """V3: Verify the generated script file exists."""
        script_path = payload["generated_script"]
        if not os.path.isfile(script_path):
            msg = f"Generated script not found: {script_path}"
            self.logger.error("V3 FAILED - %s", msg)
            raise FileValidationError(msg)

        self.logger.debug(
            "V3 PASSED - Script exists: %s", script_path
        )

    # ── V4: Workspace directory exists ──

    def _check_workspace_exists(self, payload: dict) -> None:
        """V4: Verify the workspace directory exists."""
        workspace = payload["workspace_dir"]
        if not os.path.isdir(workspace):
            msg = f"Workspace directory not found: {workspace}"
            self.logger.error("V4 FAILED - %s", msg)
            raise FileValidationError(msg)

        self.logger.debug(
            "V4 PASSED - Workspace exists: %s", workspace
        )

    # ── V5: Path security (no traversal, workspace confinement) ──

    def _check_path_security(self, payload: dict) -> None:
        """
        V5: Verify the script path is inside the workspace.
        This check aligns with Module 7 (Policy Check) rules:
        - deny ../ traversal
        - deny symlink escapes
        - all paths must be within /workspace/
        """
        script_path = os.path.realpath(payload["generated_script"])
        workspace = os.path.realpath(payload["workspace_dir"])

        # Check for '..' in the raw path (before realpath resolves it)
        raw_script = payload["generated_script"]
        if ".." in raw_script:
            msg = (
                f"Path traversal detected in script path: "
                f"{raw_script}"
            )
            self.logger.error("V5 FAILED - %s", msg)
            raise PathSecurityError(msg)

        # Check that resolved script path starts with workspace + separator
        # Using os.sep prevents false positives where workspace="/home/project"
        # would incorrectly match script_path="/home/project-backup/script.py"
        if not (script_path == workspace or script_path.startswith(workspace + os.sep)):
            msg = (
                f"Script path '{script_path}' is outside "
                f"workspace '{workspace}'"
            )
            self.logger.error("V5 FAILED - %s", msg)
            raise PathSecurityError(msg)

        self.logger.debug(
            "V5 PASSED - Script is inside workspace"
        )

    # ── V6: Venv validity (conditional) ──

    def _check_venv_if_created(self, payload: dict) -> None:
        """
        V6: If venv_created is True, verify the venv exists
        and contains a valid Python binary.
        """
        if not payload.get("venv_created", False):
            self.logger.debug(
                "V6 SKIPPED - No venv was created"
            )
            return

        venv_path = payload.get("venv_path")
        if not venv_path:
            msg = (
                "venv_created is True but venv_path "
                "is missing from the payload"
            )
            self.logger.error("V6 FAILED - %s", msg)
            raise MissingFieldError(msg)

        # Check the venv directory exists
        if not os.path.isdir(venv_path):
            msg = f"Venv directory not found: {venv_path}"
            self.logger.error("V6 FAILED - %s", msg)
            raise FileValidationError(msg)

        # Check the Python binary inside the venv
        # (Linux/macOS: bin/python, Windows: Scripts/python.exe)
        if sys.platform == "win32":
            python_bin = os.path.join(
                venv_path, "Scripts", "python.exe"
            )
        else:
            python_bin = os.path.join(
                venv_path, "bin", "python"
            )
        if not os.path.isfile(python_bin):
            msg = (
                f"Venv Python binary not found: {python_bin}"
            )
            self.logger.error("V6 FAILED - %s", msg)
            raise FileValidationError(msg)

        self.logger.debug(
            "V6 PASSED - Venv is valid at: %s", venv_path
        )

    # ── V7: Requirements consistency ──

    def _check_requirements_consistency(self, payload: dict) -> None:
        """
        V7: Warn if requirements list is empty but script likely
        has imports. This is a non-blocking warning.
        """
        requirements = payload.get("requirements", [])
        if not requirements:
            self.logger.warning(
                "V7 WARNING - Requirements list is empty. "
                "If the script has import statements, "
                "Raymond may encounter ModuleNotFoundError. "
                "Continuing anyway."
            )
        else:
            self.logger.debug(
                "V7 PASSED - %d requirements listed: %s",
                len(requirements), requirements
            )

    # V8: Check for interactive input() calls (sandbox compatibility)
    def _check_interactive_input(self, payload: dict) -> None:
        """V8: Detect and log warning for code with input() calls that won't work in sandbox."""
        script_path = payload["generated_script"]

        if not os.path.isfile(script_path):
            self.logger.debug("V8 SKIP - Script file doesn't exist")
            return

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                script_content = f.read()
        except Exception as e:
            self.logger.debug("V8 SKIP - Could not read script: %s", e)
            return

        # Patterns that indicate interactive input unsuitable for sandboxed execution
        banned_patterns = [
            r'\binput\s*\(',           # input(...)
            r'\braw_input\s*\(',       # raw_input(...) (Python 2)
            r'sys\.stdin\.read',       # sys.stdin.read()
            r'sys\.stdin\.readline',   # sys.stdin.readline()
            r'\bgetpass\.getpass',     # getpass.getpass(...)
        ]

        for i, line in enumerate(script_content.split('\n'), 1):
            # Skip comments
            code_part = line.split('#')[0]
            for pattern in banned_patterns:
                if re.search(pattern, code_part):
                    msg = (f"V8 WARNING - Script contains interactive input() at line {i}: '{line.strip()}'. "
                           "This will fail in sandboxed execution (EOFError). "
                           "Will trigger debug loop to fix.")
                    self.logger.warning(msg)
                    return  # Log warning but don't fail — let execution reveal the issue

        self.logger.debug("V8 PASSED - No dangerous interactive input detected")


# ──────────────────────────────────────────────
# EnvironmentPreparer (Schema A → Schema B)
# ──────────────────────────────────────────────

class EnvironmentPreparer:
    """
    Transforms a validated generation_output (Schema A) into
    an execution_context (Schema B) that Raymond's debugging
    module can consume directly.

    The key decision is whether a venv exists:
    - If YES: use the venv's Python and set env vars.
    - If NO:  use system python3 and flag pending installs.

    Usage:
        preparer = EnvironmentPreparer()
        exec_ctx = preparer.prepare(validated_payload)
    """

    def __init__(self):
        self.logger = logging.getLogger("orchestrator.preparer")

    def prepare(self, payload: dict) -> dict:
        """
        Transform Schema A (generation_output) into Schema B
        (execution_context).

        Args:
            payload: A validated generation_output dictionary.

        Returns:
            An execution_context dictionary ready for Raymond.
        """
        self.logger.info(
            "Preparing execution context for task: %s",
            payload["task_id"]
        )

        # Start building Schema B
        exec_context = {
            "script_path": payload["generated_script"],
            "working_dir": payload["workspace_dir"],
            "task_id": payload["task_id"],
        }

        # The key branching logic: venv or no venv
        if payload.get("venv_created") and payload.get("venv_path"):
            exec_context = self._prepare_with_venv(
                exec_context, payload["venv_path"]
            )
        else:
            exec_context = self._prepare_without_venv(
                exec_context, payload.get("requirements", [])
            )

        self.logger.info(
            "Execution context ready. "
            "Python executable: %s | "
            "Pending installs: %d",
            exec_context["python_executable"],
            len(exec_context.get("pending_installs", []))
        )

        # Forward original_prompt if present so the debugger always has
        # access to the user's raw intent (Change 1 — Phase 6 Orchestrator
        # optimisations). Placed at top level so it is immediately visible
        # to CodeDebugger without nested dict traversal.
        if "original_prompt" in payload:
            exec_context["original_prompt"] = payload["original_prompt"]

        return exec_context

    def _prepare_with_venv(
        self, exec_context: dict, venv_path: str
    ) -> dict:
        """
        Configure execution context to use the virtual
        environment that Joe's module created.
        """
        # Windows: Scripts/, Linux/macOS: bin/
        if sys.platform == "win32":
            venv_bin = os.path.join(venv_path, "Scripts")
            venv_python = os.path.join(venv_bin, "python.exe")
        else:
            venv_bin = os.path.join(venv_path, "bin")
            venv_python = os.path.join(venv_bin, "python")

        exec_context["python_executable"] = venv_python
        exec_context["env_vars"] = {
            "VIRTUAL_ENV": venv_path,
            "PATH": (
                venv_bin
                + os.pathsep
                + os.environ.get("PATH", "")
            ),
        }

        self.logger.debug(
            "Venv mode: using %s", venv_python
        )
        return exec_context

    def _prepare_without_venv(
        self, exec_context: dict, requirements: list
    ) -> dict:
        """
        Configure execution context with system Python.
        Flag any requirements as pending installs so Raymond's
        error classifier can resolve ModuleNotFoundError
        using the correct package names.
        """
        exec_context["python_executable"] = SYSTEM_PYTHON
        exec_context["env_vars"] = {}

        if requirements:
            exec_context["pending_installs"] = requirements
            self.logger.debug(
                "No-venv mode: %d packages flagged "
                "as pending installs",
                len(requirements)
            )
        else:
            self.logger.debug(
                "No-venv mode: no pending installs"
            )

        return exec_context


# ──────────────────────────────────────────────
# Convenience function for the Orchestrator loop
# ──────────────────────────────────────────────

def process_handoff(generation_output: dict) -> dict:
    """
    One-call convenience function that validates the
    generation output and prepares the execution context.

    This is what the Orchestrator's main loop calls after
    Joe's Code Generation module completes.

    Args:
        generation_output: Schema A payload from Joe's module.

    Returns:
        Schema B (execution_context) for Raymond's module.

    Raises:
        HandoffValidationError: If any validation check fails.
    """
    validator = HandoffValidator()
    preparer = EnvironmentPreparer()

    # Step 1: Validate Schema A
    validated = validator.validate(generation_output)

    # Step 2: Transform into Schema B
    exec_context = preparer.prepare(validated)

    return exec_context


# ──────────────────────────────────────────────
# Example / self-test
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # Configure logging to see validation output
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    # Example Schema A payload (would come from Joe's module)
    example_generation_output = {
        "task_id": "gen_001",
        "generated_script": "/workspace/output/stock_price.py",
        "requirements": ["yfinance==0.2.31", "pandas>=2.0"],
        "requirements_file": "/workspace/output/requirements.txt",
        "workspace_dir": "/workspace/output",
        "venv_created": False,
        "generation_status": "success",
        "metadata": {
            "complexity": "medium",
            "domain": "finance",
            "estimated_libraries": 2,
            "generation_timestamp": "2026-03-10T14:30:00Z",
        },
    }

    print("=" * 60)
    print("HANDOFF VALIDATION TEST")
    print("=" * 60)

    try:
        exec_ctx = process_handoff(example_generation_output)
        print("\nExecution Context (Schema B):")
        print(json.dumps(exec_ctx, indent=2))
    except HandoffValidationError as e:
        print(f"\nValidation FAILED: {e}")
        print(
            "(This is expected if /workspace/output/ "
            "does not exist on this machine.)"
        )