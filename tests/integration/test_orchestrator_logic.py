"""
tests/integration/test_orchestrator_logic.py
=============================================
Integration tests for the Orchestrator's pure-logic components.

These tests verify:
  1. Termination rules (MAX_DEBUG_ITERATIONS, MAX_SAME_ERROR_COUNT,
     SESSION_TIMEOUT_SECONDS) via a mocked CodeDebugger
  2. run_debug() building Schema B correctly from a script path
  3. memory_store integration: record_outcome called with correct args
  4. Graceful degradation when modules are unavailable

Strategy: we use unittest.mock.patch to replace external dependencies
(CodeDebugger, memory_store) with controlled fakes so the Orchestrator's
own logic can be tested in isolation — no LLM, no Docker required.
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, call


# ── Import Orchestrator constants we want to verify ───────────────────────────
import orchestrator as _orch_module
from orchestrator import (
    Orchestrator,
    SubprocessExecutor,
    _ExecutionResult,
    MAX_DEBUG_ITERATIONS,
    MAX_SAME_ERROR_COUNT,
    MAX_HANDOFF_RETRIES,
    SESSION_TIMEOUT_SECONDS,
)


# ── Helper: create a minimal Schema B dict for testing ────────────────────────

def _make_schema_b(script_path: str) -> dict:
    return {
        "script_path": script_path,
        "working_dir": str(Path(script_path).parent),
        "python_executable": sys.executable,
        "env_vars": {},
        "task_id": "test_task_001",
    }


# ── Helper: a fake debugger result ────────────────────────────────────────────

def _debug_result(status: str, iterations: int = 1, error: str = "") -> dict:
    return {
        "status":     status,
        "iterations": iterations,
        "error":      error,
        "stdout":     "",
        "stderr":     error,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Termination constants
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestTerminationConstants:
    """
    The termination constants are declared in orchestrator.py.
    Changing them accidentally would break the agent's safety limits.
    """

    def test_max_debug_iterations_is_10(self):
        assert MAX_DEBUG_ITERATIONS == 10

    def test_max_same_error_count_is_3(self):
        assert MAX_SAME_ERROR_COUNT == 3

    def test_max_handoff_retries_is_2(self):
        assert MAX_HANDOFF_RETRIES == 2

    def test_session_timeout_is_30_minutes(self):
        assert SESSION_TIMEOUT_SECONDS == 1800


# ═══════════════════════════════════════════════════════════════════════════════
# SubprocessExecutor (the Docker fallback)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestSubprocessExecutor:
    """
    SubprocessExecutor is the fallback when Docker is unavailable.
    It must behave like DockerExecutor's interface.
    """

    def test_execute_hello_world_returns_zero(self):
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute("print('hello')\n")
        assert result.return_code == 0
        assert "hello" in result.stdout

    def test_execute_syntax_error_returns_nonzero(self):
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute("def bad syntax !!!\n")
        assert result.return_code != 0

    def test_execute_returns_execution_result_fields(self):
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute("print('ok')\n")
        assert hasattr(result, "return_code")
        assert hasattr(result, "stdout")
        assert hasattr(result, "stderr")
        assert hasattr(result, "execution_time")
        assert hasattr(result, "timed_out")

    def test_execute_captures_stdout(self):
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute("print('MARKER_12345')\n")
        assert "MARKER_12345" in result.stdout

    def test_execute_captures_stderr(self):
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute("import sys; sys.stderr.write('ERR_MARKER')\n")
        assert "ERR_MARKER" in result.stderr

    def test_timeout_sets_timed_out_flag(self):
        ex = SubprocessExecutor(timeout=1)
        result = ex.execute("import time; time.sleep(10)\n")
        assert result.timed_out is True
        assert result.return_code == -1

    def test_execute_with_packages_runs_code(self):
        """execute_with_packages with an empty list must behave like execute."""
        ex = SubprocessExecutor(timeout=10)
        result = ex.execute_with_packages("print('pkg_test')\n", [])
        assert result.return_code == 0
        assert "pkg_test" in result.stdout


# ═══════════════════════════════════════════════════════════════════════════════
# _ExecutionResult
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestExecutionResultMimic:
    """_ExecutionResult must mirror DockerExecutor's ExecutionResult interface."""

    def test_all_attributes_accessible(self):
        r = _ExecutionResult(
            return_code=0,
            stdout="out",
            stderr="err",
            execution_time=1.5,
            timed_out=False,
            error_type=None,
        )
        assert r.return_code    == 0
        assert r.stdout         == "out"
        assert r.stderr         == "err"
        assert r.execution_time == 1.5
        assert r.timed_out      is False
        assert r.error_type     is None

    def test_error_type_can_be_set(self):
        r = _ExecutionResult(
            return_code=-1, stdout="", stderr="",
            execution_time=30.0, timed_out=True,
            error_type="TimeoutError",
        )
        assert r.error_type == "TimeoutError"


# ═══════════════════════════════════════════════════════════════════════════════
# run_debug() — Schema B construction and flow
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestRunDebugMode:

    def test_run_debug_returns_error_for_missing_script(self, tmp_path):
        """run_debug must return an error dict when the script does not exist."""
        orch = Orchestrator()
        result = orch.run_debug(str(tmp_path / "nonexistent.py"))
        assert result["status"] == "error"
        assert "not found" in result["error"].lower() or "error" in result["status"]

    def test_run_debug_with_simple_script_succeeds(self, tmp_path):
        """
        run_debug on a valid working script must return status=success
        when the CodeDebugger is mocked to return success immediately.
        """
        script = tmp_path / "working.py"
        script.write_text("print('hello')\n", encoding="utf-8")

        mock_result = _debug_result("success", iterations=0)

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger:
            MockDebugger.return_value.debug.return_value = mock_result
            orch = Orchestrator()
            result = orch.run_debug(str(script))

        assert result["status"] == "success"

    def test_run_debug_passes_schema_b_to_debugger(self, tmp_path):
        """run_debug must pass a correctly-structured Schema B to CodeDebugger.debug."""
        script = tmp_path / "test.py"
        script.write_text("x = 1\n", encoding="utf-8")

        received_schema_b = {}

        def capture_debug(schema_b):
            received_schema_b.update(schema_b)
            return _debug_result("success", iterations=1)

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger:
            MockDebugger.return_value.debug.side_effect = capture_debug
            orch = Orchestrator()
            orch.run_debug(str(script))

        assert "script_path" in received_schema_b
        assert "task_id"     in received_schema_b
        assert "working_dir" in received_schema_b
        assert os.path.isabs(received_schema_b["script_path"])

    def test_run_debug_result_contains_task_id(self, tmp_path):
        script = tmp_path / "test.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger:
            MockDebugger.return_value.debug.return_value = \
                _debug_result("success")
            orch = Orchestrator()
            result = orch.run_debug(str(script))

        assert "task_id" in result
        assert result["task_id"].startswith("dbg_")

    def test_run_debug_when_debugging_unavailable(self, tmp_path):
        """When DEBUGGING_AVAILABLE=False, run_debug must return status=failure."""
        script = tmp_path / "test.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        with patch.object(_orch_module, "DEBUGGING_AVAILABLE", False):
            orch = Orchestrator()
            result = orch.run_debug(str(script))

        assert result["status"] == "failure"
        assert "debug" in result["error"].lower() or "service" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Session timeout
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestSessionTimeout:

    def test_timeout_prevents_debug_loop(self, tmp_path):
        """
        If the session has already been running for longer than
        SESSION_TIMEOUT_SECONDS, _run_debug_loop must return failure
        without calling CodeDebugger at all.
        """
        script = tmp_path / "test.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger:
            orch = Orchestrator()
            # Fake that the session started 31 minutes ago
            orch.session_start = datetime.now() - timedelta(
                seconds=SESSION_TIMEOUT_SECONDS + 60
            )
            schema_b = _make_schema_b(str(script))
            result = orch._run_debug_loop(schema_b, "timeout_test")

        assert result["status"] == "failure"
        assert "timeout" in result["error"].lower()
        # The debugger must never have been called
        MockDebugger.return_value.debug.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# memory_store integration
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestMemoryStoreIntegration:
    """
    Verify that run_debug() calls memory_store.record_outcome() with the
    correct arguments after the debug loop completes.

    We patch _memory_store inside the orchestrator module so the real
    memory_store.json on disk is never touched.
    """

    def test_record_outcome_called_after_successful_debug(self, tmp_path):
        script = tmp_path / "ok.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        mock_memory = MagicMock()

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger, \
           patch.object(_orch_module, "_memory_store", mock_memory):

            MockDebugger.return_value.debug.return_value = \
                _debug_result("success", iterations=2)
            orch = Orchestrator()
            orch.run_debug(str(script))

        mock_memory.record_outcome.assert_called_once()
        call_kwargs = mock_memory.record_outcome.call_args[1]
        assert call_kwargs.get("mode")   == "debug"
        assert call_kwargs.get("status") == "success"

    def test_record_outcome_called_after_failed_debug(self, tmp_path):
        script = tmp_path / "broken.py"
        script.write_text("1/0\n", encoding="utf-8")

        mock_memory = MagicMock()

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger, \
           patch.object(_orch_module, "_memory_store", mock_memory):

            MockDebugger.return_value.debug.return_value = \
                _debug_result("failure", iterations=10,
                              error="max iterations reached")
            orch = Orchestrator()
            orch.run_debug(str(script))

        mock_memory.record_outcome.assert_called_once()
        call_kwargs = mock_memory.record_outcome.call_args[1]
        assert call_kwargs.get("status") != "success"

    def test_memory_store_failure_does_not_crash_pipeline(self, tmp_path):
        """If record_outcome raises, run_debug must still return a result."""
        script = tmp_path / "ok.py"
        script.write_text("print('ok')\n", encoding="utf-8")

        mock_memory = MagicMock()
        mock_memory.record_outcome.side_effect = RuntimeError("disk full")

        with patch.object(
            _orch_module, "DEBUGGING_AVAILABLE", True
        ), patch("orchestrator.CodeDebugger") as MockDebugger, \
           patch.object(_orch_module, "_memory_store", mock_memory):

            MockDebugger.return_value.debug.return_value = \
                _debug_result("success")
            orch = Orchestrator()
            result = orch.run_debug(str(script))   # must not raise

        assert "status" in result
