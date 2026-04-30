"""
tests/unit/test_handoff_validator.py
=====================================
Unit tests for HandoffValidator (orchestrator_handoff.py).

Covers every validation check V1 through V8 using:
  - Equivalence class partitioning  (valid class + invalid classes per check)
  - Boundary-value analysis         (missing single field, missing all fields)
  - Positive testing (test-to-pass)
  - Negative testing (test-to-fail)

All tests are fully isolated — no LLM, no Docker, no Ollama needed.
The workspace is provided by the shared `workspace` fixture (conftest.py).
"""

import os
import sys
import pytest

from orchestrator_handoff import (
    HandoffValidator,
    MissingFieldError,
    GenerationFailedError,
    FileValidationError,
    PathSecurityError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _copy(base: dict, **overrides) -> dict:
    """Return a shallow copy of base with the given keys overridden."""
    result = dict(base)
    result.update(overrides)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# V1 — Required fields present
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV1RequiredFields:
    """
    V1 verifies that every top-level required field and every required
    metadata sub-field is present in the payload.

    Required top-level: task_id, generated_script, requirements,
                        workspace_dir, venv_created, generation_status, metadata
    Required metadata:  complexity, domain, estimated_libraries,
                        generation_timestamp
    """

    def test_valid_payload_passes_v1(self, valid_schema_a):
        """A fully-complete payload must pass V1 without raising."""
        v = HandoffValidator()
        # validate() runs all checks V1-V8; we call _check_required_fields directly
        # to isolate V1 from filesystem-dependent checks.
        v._check_required_fields(valid_schema_a)   # must not raise

    @pytest.mark.parametrize("missing_field", [
        "task_id",
        "generated_script",
        "requirements",
        "workspace_dir",
        "venv_created",
        "generation_status",
        "metadata",
    ])
    def test_missing_top_level_field_raises(self, valid_schema_a, missing_field):
        """Each individually-missing top-level field must trigger MissingFieldError."""
        payload = dict(valid_schema_a)
        del payload[missing_field]
        v = HandoffValidator()
        with pytest.raises(MissingFieldError):
            v._check_required_fields(payload)

    @pytest.mark.parametrize("missing_meta_field", [
        "complexity",
        "domain",
        "estimated_libraries",
        "generation_timestamp",
    ])
    def test_missing_metadata_subfield_raises(self, valid_schema_a, missing_meta_field):
        """Each individually-missing metadata sub-field must trigger MissingFieldError."""
        payload = dict(valid_schema_a)
        payload["metadata"] = dict(payload["metadata"])
        del payload["metadata"][missing_meta_field]
        v = HandoffValidator()
        with pytest.raises(MissingFieldError):
            v._check_required_fields(payload)

    def test_empty_payload_raises(self):
        """An entirely empty dict must trigger MissingFieldError."""
        v = HandoffValidator()
        with pytest.raises(MissingFieldError):
            v._check_required_fields({})

    def test_error_message_names_the_missing_field(self, valid_schema_a):
        """The exception message should mention which field is missing."""
        payload = dict(valid_schema_a)
        del payload["task_id"]
        v = HandoffValidator()
        with pytest.raises(MissingFieldError, match="task_id"):
            v._check_required_fields(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V2 — Generation status is "success"
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV2GenerationStatus:
    """
    V2 verifies that generation_status == "success".
    Any other value must raise GenerationFailedError.
    """

    def test_success_status_passes(self, valid_schema_a):
        v = HandoffValidator()
        v._check_generation_status(valid_schema_a)   # must not raise

    @pytest.mark.parametrize("bad_status", [
        "failure",
        "error",
        "pending",
        "",
        "SUCCESS",      # case-sensitive: capital letters must fail
        "  success  ",  # whitespace variants must fail
    ])
    def test_non_success_status_raises(self, valid_schema_a, bad_status):
        payload = _copy(valid_schema_a, generation_status=bad_status)
        v = HandoffValidator()
        with pytest.raises(GenerationFailedError):
            v._check_generation_status(payload)

    def test_error_message_contains_actual_status(self, valid_schema_a):
        """The error message should include the actual wrong status value."""
        payload = _copy(valid_schema_a, generation_status="pending")
        v = HandoffValidator()
        with pytest.raises(GenerationFailedError, match="pending"):
            v._check_generation_status(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V3 — Generated script file exists on disk
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV3ScriptExists:
    """
    V3 verifies that the file at generated_script actually exists.
    The workspace fixture creates a real main.py, so the valid case works.
    """

    def test_existing_script_passes(self, valid_schema_a):
        v = HandoffValidator()
        v._check_script_exists(valid_schema_a)   # must not raise

    def test_nonexistent_script_raises(self, valid_schema_a):
        payload = _copy(valid_schema_a,
                        generated_script="/this/path/does/not/exist.py")
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_script_exists(payload)

    def test_directory_instead_of_file_raises(self, valid_schema_a, tmp_path):
        """Passing a directory path instead of a file must raise FileValidationError."""
        payload = _copy(valid_schema_a, generated_script=str(tmp_path))
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_script_exists(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V4 — Workspace directory exists
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV4WorkspaceExists:
    """
    V4 verifies that workspace_dir points to an existing directory.
    """

    def test_existing_workspace_passes(self, valid_schema_a):
        v = HandoffValidator()
        v._check_workspace_exists(valid_schema_a)   # must not raise

    def test_nonexistent_workspace_raises(self, valid_schema_a):
        payload = _copy(valid_schema_a, workspace_dir="/no/such/directory")
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_workspace_exists(payload)

    def test_file_instead_of_directory_raises(self, valid_schema_a):
        """Passing a file path for workspace_dir must raise FileValidationError."""
        script_path = valid_schema_a["generated_script"]   # this is a file
        payload = _copy(valid_schema_a, workspace_dir=script_path)
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_workspace_exists(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V5 — Path security (no traversal, workspace confinement)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV5PathSecurity:
    """
    V5 verifies that the script is inside the workspace.
    Specifically it catches:
      - '..' traversal in raw path strings
      - Script resolved outside the workspace directory
    """

    def test_script_inside_workspace_passes(self, valid_schema_a):
        v = HandoffValidator()
        v._check_path_security(valid_schema_a)   # must not raise

    def test_dotdot_in_script_path_raises(self, valid_schema_a, tmp_path):
        """A '..' component in the script path must raise PathSecurityError."""
        # Build a path that contains '..' even if it resolves to something valid
        unsafe = str(tmp_path / ".." / "main.py")
        payload = _copy(valid_schema_a, generated_script=unsafe)
        v = HandoffValidator()
        with pytest.raises(PathSecurityError):
            v._check_path_security(payload)

    def test_script_outside_workspace_raises(self, valid_schema_a, tmp_path):
        """
        A script that lives outside the declared workspace must be rejected.
        We create a second temp directory to act as the external location.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as external_dir:
            external_script = os.path.join(external_dir, "outside.py")
            with open(external_script, "w") as f:
                f.write("print('outside')\n")
            payload = _copy(valid_schema_a, generated_script=external_script)
            v = HandoffValidator()
            with pytest.raises(PathSecurityError):
                v._check_path_security(payload)

    def test_absolute_path_escape_raises(self, valid_schema_a):
        """An absolute path that escapes to /etc must be rejected."""
        payload = _copy(valid_schema_a, generated_script="/etc/passwd")
        v = HandoffValidator()
        with pytest.raises(PathSecurityError):
            v._check_path_security(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V6 — Venv validity (conditional on venv_created=True)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV6VenvValidity:
    """
    V6 is conditional: if venv_created is False it is silently skipped.
    If True, the venv directory and its Python binary must exist.
    """

    def test_venv_not_created_is_skipped(self, valid_schema_a):
        """venv_created=False means V6 is skipped; no exception raised."""
        payload = _copy(valid_schema_a, venv_created=False, venv_path=None)
        v = HandoffValidator()
        v._check_venv_if_created(payload)   # must not raise

    def test_valid_venv_passes(self, valid_schema_a, venv_stub):
        """venv_created=True with a correct venv layout must pass."""
        payload = _copy(valid_schema_a,
                        venv_created=True,
                        venv_path=str(venv_stub))
        v = HandoffValidator()
        v._check_venv_if_created(payload)   # must not raise

    def test_venv_created_true_but_path_missing_raises(self, valid_schema_a):
        """venv_created=True without a venv_path must raise MissingFieldError."""
        payload = _copy(valid_schema_a, venv_created=True, venv_path=None)
        v = HandoffValidator()
        with pytest.raises(MissingFieldError):
            v._check_venv_if_created(payload)

    def test_venv_directory_not_found_raises(self, valid_schema_a):
        """venv_created=True with a non-existent path must raise FileValidationError."""
        payload = _copy(valid_schema_a,
                        venv_created=True,
                        venv_path="/no/such/venv")
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_venv_if_created(payload)

    def test_venv_missing_python_binary_raises(self, valid_schema_a, tmp_path):
        """A venv directory that exists but has no Python binary must raise."""
        broken_venv = tmp_path / "broken_venv"
        broken_venv.mkdir()
        # Create bin/ directory but no python binary inside it
        (broken_venv / "bin").mkdir()
        payload = _copy(valid_schema_a,
                        venv_created=True,
                        venv_path=str(broken_venv))
        v = HandoffValidator()
        with pytest.raises(FileValidationError):
            v._check_venv_if_created(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# V7 — Requirements consistency (non-blocking warning)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV7RequirementsConsistency:
    """
    V7 is non-blocking: it emits a warning when requirements is empty but
    never raises. We verify both the passing case and the warning-only case.
    """

    def test_non_empty_requirements_passes_silently(self, valid_schema_a):
        v = HandoffValidator()
        v._check_requirements_consistency(valid_schema_a)   # must not raise

    def test_empty_requirements_does_not_raise(self, valid_schema_a):
        """Empty requirements list emits a warning but must NOT raise."""
        payload = _copy(valid_schema_a, requirements=[])
        v = HandoffValidator()
        v._check_requirements_consistency(payload)   # must not raise

    def test_v7_warning_logged_for_empty_requirements(
        self, valid_schema_a, caplog
    ):
        """The warning about empty requirements should appear in logs."""
        import logging
        payload = _copy(valid_schema_a, requirements=[])
        v = HandoffValidator()
        with caplog.at_level(logging.WARNING, logger="orchestrator.validator"):
            v._check_requirements_consistency(payload)
        # At least one WARNING record must have been emitted
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# V8 — Interactive input detection
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestV8InteractiveInput:
    """
    V8 scans the generated script for patterns that would break in a
    sandboxed (non-interactive) execution environment.

    Detected patterns trigger a WARNING (not an exception), so we verify
    that a warning is logged but no exception is raised.

    Clean scripts must produce no warning.
    """

    # ── Patterns that SHOULD produce a warning ──────────────────────────────

    @pytest.mark.parametrize("dangerous_code, pattern_name", [
        ("result = input('Enter value: ')\nprint(result)\n",  "input()"),
        ("import sys\ndata = sys.stdin.read()\n",             "sys.stdin.read"),
        ("import sys\nline = sys.stdin.readline()\n",         "sys.stdin.readline"),
        ("import getpass\npwd = getpass.getpass()\n",         "getpass.getpass"),
    ])
    def test_dangerous_pattern_triggers_warning(
        self, valid_schema_a, script_file, caplog, dangerous_code, pattern_name
    ):
        """Scripts containing interactive input patterns must log a WARNING."""
        import logging
        path = script_file(dangerous_code)
        payload = _copy(valid_schema_a, generated_script=path)
        v = HandoffValidator()
        with caplog.at_level(logging.WARNING, logger="orchestrator.validator"):
            v._check_interactive_input(payload)   # must not raise
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1, (
            f"Expected a WARNING for pattern '{pattern_name}' but none was logged."
        )

    def test_dangerous_pattern_does_not_raise(
        self, valid_schema_a, script_file
    ):
        """Even with input(), V8 must NOT raise — it only warns."""
        path = script_file("x = input('prompt: ')\n")
        payload = _copy(valid_schema_a, generated_script=path)
        v = HandoffValidator()
        v._check_interactive_input(payload)   # must not raise

    # ── Clean code must not generate any warning ────────────────────────────

    @pytest.mark.parametrize("clean_code, description", [
        ("print('hello world')\n",                       "simple print"),
        ("import os\nprint(os.getcwd())\n",              "os import only"),
        ("x = 42\nprint(x)\n",                           "arithmetic"),
        ("# input() is commented out\nprint('ok')\n",   "input in comment"),
    ])
    def test_clean_code_produces_no_warning(
        self, valid_schema_a, script_file, caplog, clean_code, description
    ):
        """Scripts without interactive input must not trigger any warning."""
        import logging
        path = script_file(clean_code)
        payload = _copy(valid_schema_a, generated_script=path)
        v = HandoffValidator()
        with caplog.at_level(logging.WARNING, logger="orchestrator.validator"):
            v._check_interactive_input(payload)
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 0, (
            f"Unexpected WARNING for clean code ({description}): "
            f"{[r.message for r in warnings]}"
        )

    def test_nonexistent_script_is_skipped_gracefully(self, valid_schema_a):
        """If the script file does not exist, V8 must skip without raising."""
        payload = _copy(valid_schema_a,
                        generated_script="/no/such/file.py")
        v = HandoffValidator()
        v._check_interactive_input(payload)   # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# Full validate() pipeline
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestFullValidatePipeline:
    """
    Tests that call the full validate() method, which runs V1-V8 in sequence.
    These catch regressions where one check accidentally suppresses another.
    """

    def test_full_validate_passes_with_valid_payload(self, valid_schema_a):
        """The complete V1-V8 pipeline must return the payload unchanged."""
        v = HandoffValidator()
        result = v.validate(valid_schema_a)
        assert result is valid_schema_a   # same object returned

    def test_full_validate_fails_fast_on_v1(self, valid_schema_a):
        """V1 failure (missing field) must prevent later checks from running."""
        payload = dict(valid_schema_a)
        del payload["task_id"]
        v = HandoffValidator()
        with pytest.raises(MissingFieldError):
            v.validate(payload)

    def test_full_validate_fails_on_v2_with_wrong_status(self, valid_schema_a):
        """V2 failure (bad status) surfaced through the full pipeline."""
        payload = _copy(valid_schema_a, generation_status="error")
        v = HandoffValidator()
        with pytest.raises(GenerationFailedError):
            v.validate(payload)

    def test_full_validate_fails_on_v3_missing_script(self, valid_schema_a):
        """V3 failure (script not found) surfaced through the full pipeline."""
        payload = _copy(valid_schema_a,
                        generated_script="/nonexistent/path/script.py",
                        workspace_dir="/nonexistent/path")
        v = HandoffValidator()
        # V3 or V4 will fire first depending on which path check runs first
        with pytest.raises((FileValidationError, PathSecurityError)):
            v.validate(payload)
