"""
agent_logger.py
===============
Module 12 — Centralized Logger

Single owner of all logging in the AI Coding Agent pipeline.
Replaces the split logging in ESIB_AiCodingAgent.py (_TeeStream / _setup_logging),
the bare print() calls in generation.py, and the logging.basicConfig() call in
orchestrator.py.

Public API
----------
    init_logger(log_dir, verbose=False) -> Path
        Set up TeeStream, human-readable .log, and structured .jsonl.
        Returns the temporary session .log path (caller renames at session end).

    close_logger()
        Flush/close the .log file and restore sys.stdout to the original stream.
        Must be called in the main() finally block before the log-rename step.

    log(source, event_type, payload, level="INFO")
        Append one JSON line to logs/agent_events.jsonl.
        Never crashes the pipeline.

    get_logger(name) -> logging.Logger
        Return a standard Python logger that writes through the shared TeeStream.

Event-type constants (use these as the event_type argument to log())
---------------------------------------------------------------------
    SESSION_START, STEP_START, STEP_COMPLETE, LLM_CALL,
    EXECUTION_RESULT, HANDOFF, RETRY, GUARDRAILS_CHECK,
    MEMORY_WRITE, ERROR, SESSION_END
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Event type constants ───────────────────────────────────────────────────────
SESSION_START    = "SESSION_START"
STEP_START       = "STEP_START"
STEP_COMPLETE    = "STEP_COMPLETE"
LLM_CALL         = "LLM_CALL"
EXECUTION_RESULT = "EXECUTION_RESULT"
HANDOFF          = "HANDOFF"
RETRY            = "RETRY"
GUARDRAILS_CHECK = "GUARDRAILS_CHECK"
MEMORY_WRITE     = "MEMORY_WRITE"
ERROR            = "ERROR"
SESSION_END      = "SESSION_END"

# ── Module-level session state ─────────────────────────────────────────────────
_jsonl_path: Optional[Path]   = None
_log_fh                       = None   # open file handle for the .log file
_orig_stdout                  = None   # sys.stdout before TeeStream was installed
_initialized: bool            = False


# ── TeeStream ─────────────────────────────────────────────────────────────────
class _TeeStream:
    """
    Wraps an output stream so every write goes to both the original
    stream (terminal) and a log file at the same time.

    Used to capture all print() output alongside logging records
    without modifying any pipeline module.
    """

    def __init__(self, original, file_handle):
        self._orig = original
        self._file = file_handle

    def write(self, data: str) -> None:
        """Write data to terminal and log file simultaneously."""
        self._orig.write(data)
        self._file.write(data)
        self._file.flush()

    def flush(self) -> None:
        """Flush both the terminal stream and the log file."""
        self._orig.flush()
        self._file.flush()

    def fileno(self) -> int:
        """Delegate fileno to the original stream (required by some libraries)."""
        return self._orig.fileno()

    def isatty(self) -> bool:
        """Return True if the original stream is a TTY."""
        return getattr(self._orig, "isatty", lambda: False)()

    def __getattr__(self, name: str):
        return getattr(self._orig, name)


# ── Public API ────────────────────────────────────────────────────────────────

def init_logger(log_dir, verbose: bool = False) -> Path:
    """
    Initialise the logging system for the current session.

    Actions performed:
      1. Creates log_dir if it does not exist.
      2. Opens a temporary .log file (named ``session_YYYYMMDD_HHMMSS_logs.log``).
      3. Replaces sys.stdout with a _TeeStream so every print() also lands in the file.
      4. Configures the root Python logger with a StreamHandler(sys.stdout)
         so all logger.info/warning/error calls land in the same file.
      5. Records the path to ``agent_events.jsonl`` in module state.

    Args:
        log_dir: Directory where log files are stored.  Created if missing.
        verbose: If True, set root log level to DEBUG; otherwise INFO.

    Returns:
        Path to the temporary session .log file so the caller can rename it.
    """
    global _jsonl_path, _log_fh, _orig_stdout, _initialized

    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    session_ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_log    = log_dir / f"session_{session_ts}_logs.log"
    _jsonl_path = log_dir / "agent_events.jsonl"

    # Open the human-readable log file and install TeeStream
    _log_fh      = temp_log.open("w", encoding="utf-8")
    _orig_stdout = sys.stdout
    sys.stdout   = _TeeStream(_orig_stdout, _log_fh)

    # Configure root logger to write through the TeeStream
    level   = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stdout)   # sys.stdout is now TeeStream
    handler.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()   # remove any handlers added before this call
    root.addHandler(handler)

    _initialized = True
    return temp_log


def close_logger() -> None:
    """
    Flush and close the session .log file and restore sys.stdout.

    Must be called from the main() finally block before the log-rename step so
    that the rename does not race with an open file handle on Windows.
    Safe to call even if init_logger() was never called.
    """
    global _log_fh, _orig_stdout, _initialized

    if not _initialized:
        return

    try:
        if _log_fh is not None:
            _log_fh.flush()
            _log_fh.close()
    except Exception:
        pass

    try:
        if _orig_stdout is not None:
            sys.stdout = _orig_stdout
    except Exception:
        pass

    _initialized = False


def log(source: str, event_type: str, payload: dict, level: str = "INFO") -> None:
    """
    Append a structured JSON event line to ``logs/agent_events.jsonl``.

    Each line has exactly these top-level fields::

        {
            "timestamp":  "2026-04-10 12:48:22",
            "source":     "orchestrator",
            "level":      "INFO",
            "event_type": "EXECUTION_RESULT",
            "payload":    { ... }
        }

    This function never crashes the pipeline — all exceptions are silently
    swallowed so a logging failure cannot interrupt a generation or debug run.

    Args:
        source:     Module name, e.g. ``"orchestrator"``, ``"generation"``.
        event_type: One of the module-level event-type constants.
        payload:    Arbitrary dict with event-specific data.
        level:      Severity string: ``"INFO"``, ``"WARNING"``, ``"ERROR"``, etc.
    """
    global _jsonl_path

    if _jsonl_path is None:
        return

    try:
        entry = {
            "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source":     source,
            "level":      level,
            "event_type": event_type,
            "payload":    payload,
        }
        with _jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass   # never crash the pipeline


def get_logger(name: str) -> logging.Logger:
    """
    Return a standard Python logger that writes through the shared TeeStream.

    If init_logger() has not yet been called the returned logger still works —
    it just writes to whatever the root handler is at that point (typically
    stderr or nothing).

    Args:
        name: Logger name, e.g. ``"orchestrator"``, ``"ESIBAgent"``.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
