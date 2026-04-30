"""
tests/unit/test_agent_logger.py
=================================
Unit tests for agent_logger.py (Module 12 — Centralized Logger).

Key behaviours tested
---------------------
1. init_logger creates the log directory and a session .log file
2. log() writes valid JSON lines to the .jsonl file with correct keys
3. log() silently ignores errors (never-crash guarantee)
4. log() does nothing when _jsonl_path is None (uninitialized state)
5. close_logger restores sys.stdout and flushes the file handle
6. get_logger returns a standard logging.Logger
7. Event-type constants are defined as plain strings

State isolation
---------------
agent_logger uses module-level global variables (_jsonl_path, _log_fh,
_orig_stdout, _initialized). We reset them after every test using
monkeypatch + close_logger() to prevent state leakage between tests.
"""

import json
import logging
import sys
import pytest
from pathlib import Path
from typing import Optional, List, Dict, Any


# ── Ensure a clean logger state after every test ──────────────────────────────

@pytest.fixture(autouse=True)
def reset_logger_state():
    """
    Guarantee clean module state before AND after every test.
    Calls close_logger() to flush handles and restore sys.stdout.
    """
    import agent_logger
    # Ensure clean state at start
    agent_logger.close_logger()
    yield
    # Clean up at end
    agent_logger.close_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# init_logger
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestInitLogger:

    def test_creates_log_directory(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "logs"
        assert not log_dir.exists()
        agent_logger.init_logger(log_dir)
        assert log_dir.is_dir()

    def test_returns_path_to_session_log(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "logs"
        session_log = agent_logger.init_logger(log_dir)
        assert isinstance(session_log, Path)
        assert session_log.suffix == ".log"

    def test_session_log_file_created(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "logs"
        session_log = agent_logger.init_logger(log_dir)
        assert session_log.exists()

    def test_jsonl_path_set_in_log_dir(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "logs"
        agent_logger.init_logger(log_dir)
        assert agent_logger._jsonl_path is not None
        assert agent_logger._jsonl_path.parent == log_dir

    def test_jsonl_filename(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "logs"
        agent_logger.init_logger(log_dir)
        assert agent_logger._jsonl_path is not None
        assert agent_logger._jsonl_path.name == "agent_events.jsonl"

    def test_initialized_flag_set(self, tmp_path):
        import agent_logger
        assert not agent_logger._initialized
        agent_logger.init_logger(tmp_path / "logs")
        assert agent_logger._initialized

    def test_existing_directory_does_not_raise(self, tmp_path):
        import agent_logger
        log_dir = tmp_path / "existing"
        log_dir.mkdir()
        agent_logger.init_logger(log_dir)   # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# log() — JSONL output
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLogFunction:

    def _init(self, tmp_path) -> Path:
        import agent_logger
        agent_logger.init_logger(tmp_path / "logs")
        # After init_logger, _jsonl_path is guaranteed to be a Path, not None
        assert agent_logger._jsonl_path is not None
        return agent_logger._jsonl_path

    def _read_entries(self, jsonl_path: Path) -> List[Dict[str, Any]]:
        """Parse every line of the JSONL file and return a list of dicts."""
        lines = [l.strip() for l in jsonl_path.read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        return [json.loads(line) for line in lines]

    def test_log_creates_jsonl_entry(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.SESSION_START, {"task": "t1"})
        entries = self._read_entries(jsonl)
        assert len(entries) == 1

    def test_log_entry_has_required_keys(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.EXECUTION_RESULT, {"rc": 0})
        entry = self._read_entries(jsonl)[0]
        for key in ("timestamp", "source", "level", "event_type", "payload"):
            assert key in entry, f"Missing key: {key}"

    def test_log_source_field_correct(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("generation", agent_logger.LLM_CALL, {})
        entry = self._read_entries(jsonl)[0]
        assert entry["source"] == "generation"

    def test_log_event_type_field_correct(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.HANDOFF, {})
        entry = self._read_entries(jsonl)[0]
        assert entry["event_type"] == agent_logger.HANDOFF

    def test_log_payload_preserved(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        payload = {"iterations": 3, "status": "success", "error": None}
        agent_logger.log("orchestrator", agent_logger.SESSION_END, payload)
        entry = self._read_entries(jsonl)[0]
        assert entry["payload"]["iterations"] == 3
        assert entry["payload"]["status"] == "success"

    def test_log_default_level_is_info(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.STEP_START, {})
        entry = self._read_entries(jsonl)[0]
        assert entry["level"] == "INFO"

    def test_log_custom_level(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.ERROR, {}, level="ERROR")
        entry = self._read_entries(jsonl)[0]
        assert entry["level"] == "ERROR"

    def test_multiple_calls_append_multiple_lines(self, tmp_path):
        import agent_logger
        jsonl = self._init(tmp_path)
        agent_logger.log("orchestrator", agent_logger.STEP_START, {"n": 1})
        agent_logger.log("orchestrator", agent_logger.STEP_COMPLETE, {"n": 1})
        agent_logger.log("orchestrator", agent_logger.SESSION_END, {})
        entries = self._read_entries(jsonl)
        assert len(entries) == 3

    def test_log_does_nothing_when_not_initialized(self, tmp_path, monkeypatch):
        """log() when _jsonl_path is None must silently do nothing."""
        import agent_logger
        # Force _jsonl_path to None regardless of previous test state
        monkeypatch.setattr(agent_logger, "_jsonl_path", None)
        fresh_jsonl = tmp_path / "logs" / "agent_events.jsonl"
        agent_logger.log("orchestrator", agent_logger.ERROR, {"msg": "oops"})
        # No file should have been created at the fresh path
        assert not fresh_jsonl.exists()

    def test_log_never_raises_on_unserializable_payload(self, tmp_path):
        """log() must swallow exceptions for unserializable payloads."""
        import agent_logger
        self._init(tmp_path)

        class Unserializable:
            pass

        # default=str in json.dumps handles this, but verify it doesn't raise
        agent_logger.log("orchestrator", agent_logger.ERROR,
                         {"obj": Unserializable()})


# ═══════════════════════════════════════════════════════════════════════════════
# close_logger
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestCloseLogger:

    def test_close_restores_stdout(self, tmp_path):
        import agent_logger
        original_stdout = sys.stdout
        agent_logger.init_logger(tmp_path / "logs")
        # stdout is now a TeeStream
        assert sys.stdout is not original_stdout
        agent_logger.close_logger()
        assert sys.stdout is original_stdout

    def test_close_sets_initialized_to_false(self, tmp_path):
        import agent_logger
        agent_logger.init_logger(tmp_path / "logs")
        assert agent_logger._initialized
        agent_logger.close_logger()
        assert not agent_logger._initialized

    def test_close_before_init_does_not_raise(self):
        """close_logger() without prior init_logger() must not raise."""
        import agent_logger
        agent_logger.close_logger()   # must not raise


# ═══════════════════════════════════════════════════════════════════════════════
# get_logger
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGetLogger:

    def test_returns_logger_instance(self):
        import agent_logger
        lgr = agent_logger.get_logger("test_module")
        assert isinstance(lgr, logging.Logger)

    def test_logger_name_matches(self):
        import agent_logger
        lgr = agent_logger.get_logger("my_module")
        assert lgr.name == "my_module"

    def test_logger_works_without_init(self):
        """get_logger must return a usable logger even before init_logger."""
        import agent_logger
        lgr = agent_logger.get_logger("pre_init")
        lgr.info("This should not raise")


# ═══════════════════════════════════════════════════════════════════════════════
# Event-type constants
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestEventTypeConstants:

    @pytest.mark.parametrize("constant_name", [
        "SESSION_START",
        "STEP_START",
        "STEP_COMPLETE",
        "LLM_CALL",
        "EXECUTION_RESULT",
        "HANDOFF",
        "RETRY",
        "GUARDRAILS_CHECK",
        "MEMORY_WRITE",
        "ERROR",
        "SESSION_END",
    ])
    def test_constant_is_defined_and_is_string(self, constant_name):
        import agent_logger
        value = getattr(agent_logger, constant_name, None)
        assert value is not None, f"{constant_name} is not defined"
        assert isinstance(value, str), f"{constant_name} must be a string"
        assert len(value) > 0