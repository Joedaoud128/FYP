"""
tests/unit/test_environment_preparer.py
=========================================
Unit tests for EnvironmentPreparer (orchestrator_handoff.py).

EnvironmentPreparer converts a validated Schema A into Schema B.
The main branching logic is:
  - venv_created=True  → use venv's Python, set VIRTUAL_ENV + PATH env vars
  - venv_created=False → use sys.executable, populate pending_installs

Both branches are platform-aware (win32 vs POSIX paths).

All tests are fully isolated — no LLM, no Docker needed.
"""

import os
import sys
import pytest

from orchestrator_handoff import EnvironmentPreparer


# ── Required keys that every valid Schema B must contain ──────────────────────
_SCHEMA_B_REQUIRED_KEYS = {
    "script_path",
    "working_dir",
    "task_id",
    "python_executable",
    "env_vars",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Schema B structure
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestSchemaBStructure:
    """Schema B must always contain the required top-level keys."""

    def test_no_venv_schema_b_has_required_keys(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert _SCHEMA_B_REQUIRED_KEYS.issubset(schema_b.keys()), (
            f"Missing keys: {_SCHEMA_B_REQUIRED_KEYS - schema_b.keys()}"
        )

    def test_schema_b_task_id_matches_schema_a(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b["task_id"] == valid_schema_a["task_id"]

    def test_schema_b_script_path_matches_schema_a(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b["script_path"] == valid_schema_a["generated_script"]

    def test_schema_b_working_dir_matches_schema_a(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b["working_dir"] == valid_schema_a["workspace_dir"]


# ═══════════════════════════════════════════════════════════════════════════════
# No-venv branch
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestNoVenvBranch:
    """When venv_created=False, the preparer must use system Python."""

    def test_python_executable_is_sys_executable(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b["python_executable"] == sys.executable

    def test_requirements_become_pending_installs(self, valid_schema_a):
        """Non-empty requirements list must appear as pending_installs in Schema B."""
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b.get("pending_installs") == valid_schema_a["requirements"]

    def test_empty_requirements_no_pending_installs(self, valid_schema_a):
        """Empty requirements list must NOT create a pending_installs key."""
        payload = {**valid_schema_a, "requirements": []}
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        assert "pending_installs" not in schema_b

    def test_env_vars_is_empty_dict_without_venv(self, valid_schema_a):
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert schema_b["env_vars"] == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Venv branch
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestVenvBranch:
    """When venv_created=True, the preparer must configure the venv Python."""

    def test_venv_python_executable_inside_venv(self, valid_schema_a, venv_stub):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        # The executable must be inside the venv directory
        assert str(venv_stub) in schema_b["python_executable"]

    def test_venv_env_vars_contain_virtual_env(self, valid_schema_a, venv_stub):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        assert "VIRTUAL_ENV" in schema_b["env_vars"]
        assert schema_b["env_vars"]["VIRTUAL_ENV"] == str(venv_stub)

    def test_venv_env_vars_contain_path(self, valid_schema_a, venv_stub):
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        assert "PATH" in schema_b["env_vars"]

    def test_venv_path_precedes_system_path(self, valid_schema_a, venv_stub):
        """The venv bin directory must appear BEFORE the system PATH."""
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        path_value = schema_b["env_vars"]["PATH"]
        # venv bin dir comes before the os.pathsep separator
        if sys.platform == "win32":
            venv_bin = str(venv_stub / "Scripts")
        else:
            venv_bin = str(venv_stub / "bin")
        assert path_value.startswith(venv_bin)

    def test_venv_branch_uses_correct_binary_name(self, valid_schema_a, venv_stub):
        """On Windows the binary is python.exe; on POSIX it is python."""
        payload = {
            **valid_schema_a,
            "venv_created": True,
            "venv_path": str(venv_stub),
        }
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        exe = schema_b["python_executable"]
        if sys.platform == "win32":
            assert exe.endswith("python.exe")
        else:
            assert exe.endswith("python")


# ═══════════════════════════════════════════════════════════════════════════════
# original_prompt forwarding
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestOriginalPromptForwarding:
    """
    When Schema A contains an original_prompt key, it must be forwarded
    into Schema B so the debugger has access to the user's raw intent.
    """

    def test_original_prompt_forwarded_when_present(self, valid_schema_a):
        payload = {**valid_schema_a, "original_prompt": "sort a list of numbers"}
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(payload)
        assert schema_b.get("original_prompt") == "sort a list of numbers"

    def test_no_original_prompt_key_absent_from_schema_b(self, valid_schema_a):
        """If original_prompt is absent from Schema A it must not appear in Schema B."""
        assert "original_prompt" not in valid_schema_a   # sanity check on fixture
        ep = EnvironmentPreparer()
        schema_b = ep.prepare(valid_schema_a)
        assert "original_prompt" not in schema_b
