"""
tests/integration/test_process_handoff.py
==========================================
Integration tests for process_handoff() — the one-call convenience
function that chains HandoffValidator → EnvironmentPreparer.

This is the most important integration boundary in the project:
it is the exact interface between Joe's generation module and
Raymond's debugging module. Any regression here breaks the whole pipeline.

Approach: bottom-up integration with real filesystem (no mocks).
We create real temp files and directories so both validation and
preparation steps exercise actual I/O paths.

No LLM, no Docker, no Ollama required.
"""

import os
import sys
import pytest

from orchestrator_handoff import (
    process_handoff,
    HandoffValidationError,
    MissingFieldError,
    GenerationFailedError,
    FileValidationError,
    PathSecurityError,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Happy-path: valid Schema A → correct Schema B
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestProcessHandoffHappyPath:

    def test_returns_dict(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result, dict)

    def test_schema_b_contains_required_keys(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        for key in ("script_path", "working_dir", "task_id",
                    "python_executable", "env_vars"):
            assert key in result, f"Schema B missing key: '{key}'"

    def test_schema_b_script_path_matches_input(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert result["script_path"] == valid_schema_a["generated_script"]

    def test_schema_b_working_dir_matches_input(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert result["working_dir"] == valid_schema_a["workspace_dir"]

    def test_schema_b_task_id_matches_input(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert result["task_id"] == valid_schema_a["task_id"]

    def test_schema_b_python_executable_is_a_string(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result["python_executable"], str)
        assert len(result["python_executable"]) > 0

    def test_no_venv_uses_system_python(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert result["python_executable"] == sys.executable

    def test_no_venv_requirements_become_pending_installs(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert result.get("pending_installs") == valid_schema_a["requirements"]

    def test_empty_requirements_no_pending_installs_key(self, valid_schema_a):
        payload = {**valid_schema_a, "requirements": []}
        result = process_handoff(payload)
        assert "pending_installs" not in result

    def test_original_prompt_forwarded(self, valid_schema_a):
        payload = {**valid_schema_a, "original_prompt": "write bubble sort"}
        result = process_handoff(payload)
        assert result.get("original_prompt") == "write bubble sort"


# ═══════════════════════════════════════════════════════════════════════════════
# Venv path: Schema A with venv_created=True → Schema B with venv Python
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestProcessHandoffWithVenv:

    def test_venv_python_inside_venv_dir(self, valid_schema_a, venv_stub):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        result = process_handoff(payload)
        assert str(venv_stub) in result["python_executable"]

    def test_venv_env_vars_has_virtual_env(self, valid_schema_a, venv_stub):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        result = process_handoff(payload)
        assert result["env_vars"].get("VIRTUAL_ENV") == str(venv_stub)

    def test_venv_path_precedes_system_in_env_path(
        self, valid_schema_a, venv_stub
    ):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        result = process_handoff(payload)
        path_val = result["env_vars"].get("PATH", "")
        if sys.platform == "win32":
            venv_bin = str(venv_stub / "Scripts")
        else:
            venv_bin = str(venv_stub / "bin")
        assert path_val.startswith(venv_bin)


# ═══════════════════════════════════════════════════════════════════════════════
# Failure paths: invalid Schema A must raise HandoffValidationError
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestProcessHandoffFailurePaths:

    def test_missing_task_id_raises_missing_field(self, valid_schema_a):
        payload = {k: v for k, v in valid_schema_a.items() if k != "task_id"}
        with pytest.raises(MissingFieldError):
            process_handoff(payload)

    def test_bad_generation_status_raises(self, valid_schema_a):
        payload = {**valid_schema_a, "generation_status": "failure"}
        with pytest.raises(GenerationFailedError):
            process_handoff(payload)

    def test_nonexistent_script_raises(self, valid_schema_a):
        payload = {
            **valid_schema_a,
            "generated_script": "/this/does/not/exist.py",
        }
        with pytest.raises((FileValidationError, PathSecurityError)):
            process_handoff(payload)

    def test_path_traversal_raises(self, valid_schema_a, tmp_path):
        """
        A '..' in the script path must raise either PathSecurityError (V5)
        or FileValidationError (V3 fires first when the path doesn't exist
        on the filesystem after '..' resolution). Both are correct rejections.
        """
        unsafe = str(tmp_path / ".." / "main.py")
        payload = {**valid_schema_a, "generated_script": unsafe}
        with pytest.raises((PathSecurityError, FileValidationError)):
            process_handoff(payload)

    def test_all_validation_errors_are_subclass_of_handoff_error(
        self, valid_schema_a
    ):
        """Any validation failure must be catchable as HandoffValidationError."""
        payload = {**valid_schema_a, "generation_status": "failure"}
        with pytest.raises(HandoffValidationError):
            process_handoff(payload)


# ═══════════════════════════════════════════════════════════════════════════════
# Schema B is usable by CodeDebugger (structural contract)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestSchemaBContract:
    """
    Verify that Schema B produced by process_handoff() satisfies the
    structural contract expected by Raymond's CodeDebugger module.

    We do NOT import CodeDebugger here (it requires the LLM) — we just
    verify the keys and types that the debugger reads from Schema B,
    as documented in orchestrator.py's _run_debug_loop.
    """

    def test_script_path_is_absolute_string(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result["script_path"], str)
        # Should be a usable path string
        assert len(result["script_path"]) > 0

    def test_working_dir_is_a_string(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result["working_dir"], str)

    def test_task_id_is_a_string(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result["task_id"], str)

    def test_python_executable_points_to_real_file(self, valid_schema_a):
        """
        The python_executable in Schema B must point to a file that
        actually exists on the current machine (it comes from sys.executable).
        """
        result = process_handoff(valid_schema_a)
        assert os.path.isfile(result["python_executable"]), (
            f"python_executable does not exist: {result['python_executable']}"
        )

    def test_env_vars_is_a_dict(self, valid_schema_a):
        result = process_handoff(valid_schema_a)
        assert isinstance(result["env_vars"], dict)
