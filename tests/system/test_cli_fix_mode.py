"""
tests/system/test_cli_fix_mode.py
===================================
System-level (end-to-end) tests for the ESIB AI Coding Agent CLI.

These tests invoke ESIB_AiCodingAgent.py as a subprocess and verify the
process exit code and stdout output — exactly as the jury will see it.

Requirements to run these tests
--------------------------------
- A running Ollama instance with qwen3:8b available
- Python 3.10+ in the virtual environment

Because these tests require a live LLM, they are marked @pytest.mark.system
and are EXCLUDED from CI by default.

Run them manually:
    pytest tests/system/ -v -m system

Or run only the fast subset (pure subprocess, no LLM):
    pytest tests/system/ -v -m "system and not slow"

Broken scripts used in tests
-----------------------------
Each broken script represents one realistic class of bug that the
debug pipeline is designed to fix:
  1. NameError       — undefined variable
  2. ZeroDivisionError — division by zero
  3. SyntaxError     — malformed Python

These are the most reliable demo cases because:
  - The error message is always deterministic
  - The fix is always unambiguous
  - The LLM cannot hallucinate an alternative interpretation
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path


# ── Path to the CLI entry point ───────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
_CLI = str(_PROJECT_ROOT / "ESIB_AiCodingAgent.py")


# ── Helper: run the CLI and return CompletedProcess ───────────────────────────

def _run_cli(*args, timeout: int = 180) -> subprocess.CompletedProcess:
    """
    Invoke the CLI entry point as a subprocess using the current interpreter.
    Returns the CompletedProcess so tests can inspect returncode and stdout.
    """
    return subprocess.run(
        [sys.executable, _CLI, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
    )


# ── Broken script fixtures ────────────────────────────────────────────────────

@pytest.fixture()
def name_error_script(tmp_path: Path) -> str:
    """A script that fails with NameError: name 'result' is not defined."""
    script = tmp_path / "name_error.py"
    script.write_text(
        "# This script has a NameError\n"
        "numbers = [1, 2, 3, 4, 5]\n"
        "total = sum(numbers)\n"
        "print(f'Sum: {result}')  # 'result' is not defined\n",
        encoding="utf-8",
    )
    return str(script)


@pytest.fixture()
def zero_division_script(tmp_path: Path) -> str:
    """A script that fails with ZeroDivisionError."""
    script = tmp_path / "zero_div.py"
    script.write_text(
        "# This script has a ZeroDivisionError\n"
        "numerator = 100\n"
        "denominator = 0\n"
        "result = numerator / denominator\n"
        "print(f'Result: {result}')\n",
        encoding="utf-8",
    )
    return str(script)


@pytest.fixture()
def syntax_error_script(tmp_path: Path) -> str:
    """A script with a clear SyntaxError."""
    script = tmp_path / "syntax_error.py"
    script.write_text(
        "# This script has a SyntaxError\n"
        "def calculate_area(radius\n"       # missing closing parenthesis
        "    import math\n"
        "    return math.pi * radius ** 2\n"
        "\n"
        "print(calculate_area(5))\n",
        encoding="utf-8",
    )
    return str(script)


@pytest.fixture()
def working_script(tmp_path: Path) -> str:
    """A script that works perfectly — used to verify the pass-through case."""
    script = tmp_path / "working.py"
    script.write_text(
        "numbers = [1, 2, 3, 4, 5]\n"
        "total = sum(numbers)\n"
        "print(f'Sum: {total}')\n",
        encoding="utf-8",
    )
    return str(script)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI availability (no LLM required)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.system
class TestCLIAvailability:
    """Sanity checks that do not require Ollama."""

    def test_cli_script_exists(self):
        assert os.path.isfile(_CLI), f"CLI entry point not found: {_CLI}"

    def test_cli_help_flag_exits_zero(self):
        proc = _run_cli("--help", timeout=15)
        assert proc.returncode == 0, (
            f"--help exited with {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        )

    def test_cli_help_mentions_generate(self):
        proc = _run_cli("--help", timeout=15)
        assert "generate" in proc.stdout.lower() or "generate" in proc.stderr.lower()

    def test_cli_help_mentions_fix(self):
        proc = _run_cli("--help", timeout=15)
        assert "fix" in proc.stdout.lower() or "fix" in proc.stderr.lower()

    def test_cli_with_nonexistent_script_exits_nonzero(self, tmp_path):
        proc = _run_cli(
            "--fix", str(tmp_path / "ghost.py"),
            timeout=30
        )
        assert proc.returncode != 0


# ═══════════════════════════════════════════════════════════════════════════════
# Fix mode with working script (no LLM needed — should pass through)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.system
class TestFixModeWorkingScript:
    """
    A working script passed to --fix should either:
    (a) Exit 0 with a success message, OR
    (b) Complete the debug loop with 0 iterations (already working)
    No LLM call is needed if the script executes cleanly on first try.
    """

    def test_working_script_exits_zero(self, working_script):
        proc = _run_cli("--fix", working_script, timeout=60)
        assert proc.returncode == 0, (
            f"Expected exit 0 for working script but got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )

    def test_working_script_output_contains_success_indicator(
        self, working_script
    ):
        proc = _run_cli("--fix", working_script, timeout=60)
        combined = (proc.stdout + proc.stderr).lower()
        assert "success" in combined or proc.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Fix mode with broken scripts (requires running Ollama + qwen3:8b)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.system
@pytest.mark.slow
class TestFixModeBrokenScripts:
    """
    These tests require a running Ollama instance.
    They verify that the full debug pipeline successfully repairs
    common Python errors.

    Skip if Ollama is not available:
        pytest -m "system and not slow"
    """

    def test_fix_name_error_exits_zero(self, name_error_script):
        proc = _run_cli("--fix", name_error_script, timeout=180)
        assert proc.returncode == 0, (
            f"Expected exit 0 after fixing NameError but got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )

    def test_fix_name_error_output_contains_success(self, name_error_script):
        proc = _run_cli("--fix", name_error_script, timeout=180)
        combined = (proc.stdout + proc.stderr).lower()
        assert "success" in combined, (
            f"Expected 'success' in output but got:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_fix_zero_division_exits_zero(self, zero_division_script):
        proc = _run_cli("--fix", zero_division_script, timeout=180)
        assert proc.returncode == 0, (
            f"Expected exit 0 after fixing ZeroDivisionError but got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )

    def test_fix_syntax_error_exits_zero(self, syntax_error_script):
        proc = _run_cli("--fix", syntax_error_script, timeout=180)
        assert proc.returncode == 0, (
            f"Expected exit 0 after fixing SyntaxError but got {proc.returncode}\n"
            f"STDOUT:\n{proc.stdout}\n"
            f"STDERR:\n{proc.stderr}"
        )

    def test_fix_produces_stdout_output(self, name_error_script):
        """After successful fix, the corrected script must produce some output."""
        proc = _run_cli("--fix", name_error_script, timeout=180)
        assert len(proc.stdout.strip()) > 0, (
            "Expected stdout from corrected script but got nothing"
        )
