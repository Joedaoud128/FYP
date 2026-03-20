"""
test_orchestrator_handoff.py
============================
Test suite for the Orchestrator handoff code.

This file simulates what Joe's module would produce and tests
that the HandoffValidator and EnvironmentPreparer work correctly.

How to run:
    python test_orchestrator_handoff.py

What it tests:
    1. Valid payload with venv → should PASS all checks
    2. Valid payload without venv → should PASS, pending_installs set
    3. Missing required fields → should FAIL with MissingFieldError
    4. Generation failed → should FAIL with GenerationFailedError
    5. Script file doesn't exist → should FAIL with FileValidationError
    6. Path traversal attack → should FAIL with PathSecurityError
    7. Corrupted venv → should FAIL with FileValidationError
    8. Empty requirements → should PASS with warning
    9. Debug Mode with real script → should execute and return result
"""

import os
import sys
import json
import shutil
import logging
import tempfile

# ── Setup: Add the directory containing the code to Python path ──
# (Adjust this path if your files are in a different location)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from orchestrator_handoff import (
    HandoffValidator,
    EnvironmentPreparer,
    HandoffValidationError,
    MissingFieldError,
    GenerationFailedError,
    FileValidationError,
    PathSecurityError,
    process_handoff,
)

# ── Configure logging so you can see validation output ──
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)


# ══════════════════════════════════════════════
# HELPER: Create a fake workspace
# ══════════════════════════════════════════════

class FakeWorkspace:
    """
    Creates a temporary /workspace/-like directory structure
    with a fake Python script, so the validator has real files
    to check against.
    """

    def __init__(self):
        # Create a temp directory to act as our workspace
        self.base = tempfile.mkdtemp(prefix="workspace_")
        self.output_dir = os.path.join(self.base, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Create a fake generated script
        self.script_path = os.path.join(
            self.output_dir, "stock_price.py"
        )
        with open(self.script_path, "w") as f:
            f.write(
                "# Fake generated script for testing\n"
                "import yfinance as yf\n"
                "ticker = yf.Ticker('MSFT')\n"
                "print(ticker.info['currentPrice'])\n"
            )

        # Create a fake requirements.txt
        self.requirements_file = os.path.join(
            self.output_dir, "requirements.txt"
        )
        with open(self.requirements_file, "w") as f:
            f.write("yfinance==0.2.31\npandas>=2.0\n")

        # Create a fake venv with a Python binary
        self.venv_path = os.path.join(self.base, ".venv")
        # Windows uses Scripts/, Linux uses bin/
        if sys.platform == "win32":
            venv_bin = os.path.join(self.venv_path, "Scripts")
        else:
            venv_bin = os.path.join(self.venv_path, "bin")
        os.makedirs(venv_bin, exist_ok=True)
        # Create a fake python binary
        if sys.platform == "win32":
            self.venv_python = os.path.join(venv_bin, "python.exe")
        else:
            self.venv_python = os.path.join(venv_bin, "python")
        with open(self.venv_python, "w") as f:
            f.write("#!/usr/bin/env python3\n")
        os.chmod(self.venv_python, 0o755)

    def cleanup(self):
        """Remove the temporary workspace."""
        shutil.rmtree(self.base, ignore_errors=True)

    def make_valid_payload(self, with_venv=True):
        """Create a valid Schema A payload."""
        payload = {
            "task_id": "gen_test_001",
            "generated_script": self.script_path,
            "requirements": ["yfinance==0.2.31", "pandas>=2.0"],
            "requirements_file": self.requirements_file,
            "workspace_dir": self.output_dir,
            "venv_created": with_venv,
            "generation_status": "success",
            "metadata": {
                "complexity": "medium",
                "domain": "finance",
                "estimated_libraries": 2,
                "generation_timestamp": "2026-03-10T14:30:00Z",
            },
        }
        if with_venv:
            payload["venv_path"] = self.venv_path
        return payload


# ══════════════════════════════════════════════
# TEST RUNNER
# ══════════════════════════════════════════════

def run_test(name, test_func):
    """Run a single test and print pass/fail."""
    print(f"\n{'─' * 60}")
    print(f"TEST: {name}")
    print(f"{'─' * 60}")
    try:
        test_func()
        print(f"✅ PASSED: {name}")
        return True
    except AssertionError as e:
        print(f"❌ FAILED: {name} — {e}")
        return False
    except Exception as e:
        print(f"❌ ERROR:  {name} — {type(e).__name__}: {e}")
        return False


# ══════════════════════════════════════════════
# TEST 1: Valid payload WITH venv
# ══════════════════════════════════════════════

def test_valid_payload_with_venv():
    """
    A complete, valid Schema A payload with a venv.
    Should pass all V1-V7 checks and produce Schema B
    with python_executable pointing to the venv Python.
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload(with_venv=True)
        result = process_handoff(payload)

        # Verify Schema B structure
        assert "script_path" in result, "Missing script_path"
        assert "working_dir" in result, "Missing working_dir"
        assert "python_executable" in result, "Missing python_executable"
        assert "env_vars" in result, "Missing env_vars"
        assert "task_id" in result, "Missing task_id"

        # Verify venv was used
        assert "venv" in result["python_executable"].lower(), (
            f"Expected venv python, got: {result['python_executable']}"
        )
        assert "VIRTUAL_ENV" in result["env_vars"], (
            "Missing VIRTUAL_ENV in env_vars"
        )
        assert "pending_installs" not in result, (
            "pending_installs should NOT be present when venv exists"
        )

        print(f"   Schema B output:")
        print(f"   {json.dumps(result, indent=4)}")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 2: Valid payload WITHOUT venv
# ══════════════════════════════════════════════

def test_valid_payload_without_venv():
    """
    A valid payload where no venv was created.
    Should produce Schema B with python3 and pending_installs.
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload(with_venv=False)
        result = process_handoff(payload)

        assert result["python_executable"] == "python3", (
            f"Expected python3, got: {result['python_executable']}"
        )
        assert result["env_vars"] == {}, (
            "env_vars should be empty when no venv"
        )
        assert "pending_installs" in result, (
            "pending_installs should be present when no venv"
        )
        assert len(result["pending_installs"]) == 2, (
            f"Expected 2 pending installs, got {len(result['pending_installs'])}"
        )

        print(f"   Schema B output:")
        print(f"   {json.dumps(result, indent=4)}")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 3: Missing required fields
# ══════════════════════════════════════════════

def test_missing_fields():
    """
    A payload missing task_id and metadata.
    Should raise MissingFieldError (V1).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload()
        del payload["task_id"]
        del payload["metadata"]

        try:
            process_handoff(payload)
            assert False, "Should have raised MissingFieldError"
        except MissingFieldError as e:
            print(f"   Correctly caught: {e}")
            assert "task_id" in str(e) or "metadata" in str(e)
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 4: Generation status = "failed"
# ══════════════════════════════════════════════

def test_generation_failed():
    """
    A payload where generation_status is "failed".
    Should raise GenerationFailedError (V2).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload()
        payload["generation_status"] = "failed"

        try:
            process_handoff(payload)
            assert False, "Should have raised GenerationFailedError"
        except GenerationFailedError as e:
            print(f"   Correctly caught: {e}")
            assert "failed" in str(e).lower()
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 5: Script file doesn't exist
# ══════════════════════════════════════════════

def test_script_not_found():
    """
    A payload pointing to a non-existent script.
    Should raise FileValidationError (V3).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload()
        payload["generated_script"] = os.path.join(
            ws.output_dir, "nonexistent_script.py"
        )

        try:
            process_handoff(payload)
            assert False, "Should have raised FileValidationError"
        except FileValidationError as e:
            print(f"   Correctly caught: {e}")
            assert "not found" in str(e).lower()
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 6: Path traversal attack
# ══════════════════════════════════════════════

def test_path_traversal():
    """
    A payload where the script path contains '../'
    attempting to escape the workspace.
    Should raise PathSecurityError (V5).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload()
        # Attempt to reference a file outside workspace
        payload["generated_script"] = os.path.join(
            ws.output_dir, "..", "..", "etc", "passwd"
        )

        try:
            process_handoff(payload)
            assert False, "Should have raised PathSecurityError"
        except PathSecurityError as e:
            print(f"   Correctly caught: {e}")
            assert "traversal" in str(e).lower() or "outside" in str(e).lower()
        except FileValidationError:
            # This is also acceptable — the file doesn't exist,
            # so V3 may catch it before V5
            print("   Caught by V3 (file not found) before V5")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 7: Corrupted venv (no Python binary)
# ══════════════════════════════════════════════

def test_corrupted_venv():
    """
    A payload where venv_created=true but the venv's
    Python binary has been deleted.
    Should raise FileValidationError (V6).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload(with_venv=True)
        # Delete the fake Python binary to simulate corruption
        os.remove(ws.venv_python)

        try:
            process_handoff(payload)
            assert False, "Should have raised FileValidationError"
        except FileValidationError as e:
            print(f"   Correctly caught: {e}")
            assert "venv" in str(e).lower() or "python" in str(e).lower()
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 8: Empty requirements (warning only)
# ══════════════════════════════════════════════

def test_empty_requirements():
    """
    A payload with an empty requirements list.
    Should pass with a V7 warning (non-blocking).
    """
    ws = FakeWorkspace()
    try:
        payload = ws.make_valid_payload(with_venv=True)
        payload["requirements"] = []

        # Should NOT raise an exception
        result = process_handoff(payload)
        assert result is not None, "Should return a valid result"
        print(f"   Passed with warning (check logs above for V7 WARNING)")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 9: Debug Mode with a real script
# ══════════════════════════════════════════════

def test_debug_mode_real_script():
    """
    Test the Orchestrator's run_debug() entry point
    with a real Python script that succeeds.
    """
    # Import Orchestrator (only if orchestrator.py is available)
    try:
        from orchestrator import Orchestrator
    except ImportError:
        print("   SKIPPED: orchestrator.py not found in path")
        return

    # Create a simple script that succeeds
    ws = FakeWorkspace()
    try:
        success_script = os.path.join(ws.output_dir, "success.py")
        with open(success_script, "w") as f:
            f.write("print('Hello from the test script!')\n")

        orch = Orchestrator()
        result = orch.run_debug(success_script)

        assert result["status"] == "success", (
            f"Expected success, got: {result['status']}"
        )
        assert "Hello from the test script!" in result.get("output", ""), (
            f"Expected script output, got: {result.get('output', '')}"
        )
        print(f"   Result: {json.dumps(result, indent=4, default=str)}")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# TEST 10: Debug Mode with a broken script
# ══════════════════════════════════════════════

def test_debug_mode_broken_script():
    """
    Test the Orchestrator's run_debug() with a script
    that has an ImportError. Should fail after max iterations
    (since Raymond's fix module is a placeholder).
    """
    try:
        from orchestrator import Orchestrator, OrchestratorConfig
    except ImportError:
        print("   SKIPPED: orchestrator.py not found in path")
        return

    ws = FakeWorkspace()
    try:
        broken_script = os.path.join(ws.output_dir, "broken.py")
        with open(broken_script, "w") as f:
            f.write("import nonexistent_module_xyz\n")

        # Use a small iteration limit for faster testing
        config = OrchestratorConfig()
        config.MAX_ITERATIONS = 3
        config.MAX_SAME_ERROR = 2

        orch = Orchestrator(config=config)
        result = orch.run_debug(broken_script)

        # Should fail (placeholder debug module can't fix it)
        assert result["status"] == "failure", (
            f"Expected failure, got: {result['status']}"
        )
        print(f"   Correctly failed with reason: {result.get('reason')}")
        print(f"   Iterations used: {result['orchestrator_metadata']['iterations']}")
        print(f"   Error history: {result['orchestrator_metadata']['error_history']}")
    finally:
        ws.cleanup()


# ══════════════════════════════════════════════
# MAIN: Run all tests
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  ORCHESTRATOR HANDOFF TEST SUITE")
    print("=" * 60)

    tests = [
        ("1. Valid payload WITH venv",     test_valid_payload_with_venv),
        ("2. Valid payload WITHOUT venv",   test_valid_payload_without_venv),
        ("3. Missing required fields",      test_missing_fields),
        ("4. Generation status = failed",   test_generation_failed),
        ("5. Script file not found",        test_script_not_found),
        ("6. Path traversal attack",        test_path_traversal),
        ("7. Corrupted venv",               test_corrupted_venv),
        ("8. Empty requirements (warning)", test_empty_requirements),
        ("9. Debug Mode - success script",  test_debug_mode_real_script),
        ("10. Debug Mode - broken script",  test_debug_mode_broken_script),
    ]

    passed = 0
    failed = 0
    for name, func in tests:
        if run_test(name, func):
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {passed} passed, {failed} failed, "
          f"{len(tests)} total")
    print(f"{'=' * 60}")
