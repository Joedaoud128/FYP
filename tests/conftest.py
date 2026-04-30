"""
conftest.py
===========
Shared pytest fixtures used across unit, integration, and system tests.

How pytest finds this file
--------------------------
pytest auto-loads conftest.py files from the directory tree.  This file
lives at tests/ so every test module inside tests/ (and its sub-packages)
can import any fixture defined here simply by declaring it as a parameter.
No import statement is needed in the test file itself.

Fixtures defined here
---------------------
project_root      — absolute Path to the repository root (where source modules live)
workspace         — fresh temp directory per test, pre-populated with a minimal script
valid_schema_a    — fully-valid Schema A dict ready to pass HandoffValidator
script_file       — helper that writes a Python script into a temp dir and returns its path
venv_stub         — creates a fake venv directory with the correct binary layout
"""

import os
import sys
import pytest
from pathlib import Path

# ── Make source modules importable ────────────────────────────────────────────
# The source files live at the repo root (same level as the tests/ folder).
# We insert the root once here so every test file can do:
#   from orchestrator_handoff import HandoffValidator
# without any sys.path manipulation inside individual test files.

_PROJECT_ROOT = Path(__file__).parent.parent.resolve()
_SRC_DIR = _PROJECT_ROOT / "src" / "orchestrator"
_GUARDRAILS_DIR = _PROJECT_ROOT / "src" / "guardrails"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_GUARDRAILS_DIR) not in sys.path:
    sys.path.insert(0, str(_GUARDRAILS_DIR))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def project_root() -> Path:
    """Absolute path to the repository root directory."""
    return _PROJECT_ROOT


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """
    A fresh temporary directory for each test, pre-populated with a
    minimal valid Python script called 'main.py'.

    Using pytest's built-in tmp_path fixture means the directory is
    automatically cleaned up after every test — no teardown code needed.
    """
    script = tmp_path / "main.py"
    script.write_text("print('hello world')\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def valid_schema_a(workspace: Path) -> dict:
    """
    A fully-valid Schema A dict that satisfies all V1–V8 checks.

    Tests that verify *failure* cases should copy this dict and mutate
    only the one field they want to break, e.g.:

        def test_v2_bad_status(valid_schema_a):
            payload = {**valid_schema_a, "generation_status": "failure"}
            with pytest.raises(GenerationFailedError):
                HandoffValidator().validate(payload)
    """
    script_path = str(workspace / "main.py")
    return {
        "task_id":           "test_task_001",
        "generated_script":  script_path,
        "requirements":      ["requests>=2.28.0"],
        "workspace_dir":     str(workspace),
        "venv_created":      False,
        "venv_path":         None,
        "generation_status": "success",
        "metadata": {
            "complexity":          "low",
            "domain":              "general",
            "estimated_libraries": 1,
            "generation_timestamp": "2026-04-30T10:00:00Z",
        },
    }


@pytest.fixture()
def script_file(tmp_path: Path):
    """
    Factory fixture: call it with content and an optional filename to
    create a Python file inside tmp_path.

    Usage inside a test:
        def test_something(script_file):
            path = script_file("print('hello')")
            # path is a str, e.g. /tmp/pytest-xxx/.../script.py
    """
    def _make(content: str, name: str = "script.py") -> str:
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        return str(p)
    return _make


@pytest.fixture()
def venv_stub(tmp_path: Path) -> Path:
    """
    Creates a fake virtual-environment directory with the correct binary
    layout expected by V6 (HandoffValidator._check_venv_if_created).

    On Linux/macOS:  <venv>/bin/python
    On Windows:      <venv>/Scripts/python.exe

    Returns the venv root Path so tests can pass it as 'venv_path'.
    """
    venv_dir = tmp_path / "fake_venv"
    if sys.platform == "win32":
        bin_dir = venv_dir / "Scripts"
        bin_dir.mkdir(parents=True)
        (bin_dir / "python.exe").write_text("", encoding="utf-8")
    else:
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True)
        python_bin = bin_dir / "python"
        python_bin.write_text("", encoding="utf-8")
        python_bin.chmod(0o755)
    return venv_dir
