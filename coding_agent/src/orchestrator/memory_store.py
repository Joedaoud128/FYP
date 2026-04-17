"""
memory_store.py
===============
Module 10 — Persistent Memory Store

Persists error patterns and task outcomes across pipeline runs so the
orchestrator can learn from prior failures and surface resolution hints.

Storage file: src/orchestrator/memory_store/memory_store.json

JSON schema
-----------
{
    "task_outcomes": [
        {
            "task_id":          "gen_d6cd3a38",
            "timestamp":        "2026-04-10 12:48:09",
            "mode":             "generate",
            "prompt_summary":   "<first 80 chars of prompt>",
            "status":           "success",
            "total_time_s":     35.7,
            "handoff_retries":  0,
            "debug_iterations": 0,
            "error_type":       null,
            "failed_stage":     null
        }
    ],
    "error_patterns": [
        {
            "error_fingerprint": "ModuleNotFoundError:numpy",
            "source_module":     "debugging",
            "first_seen":        "2026-04-10 12:48:09",
            "last_seen":         "2026-04-10 12:48:09",
            "count":             3,
            "resolved":          true,
            "resolution":        "pip install numpy"
        }
    ]
}

Public API
----------
    record_outcome(task_id, mode, prompt, status, total_time_s, ...)
    record_error(error_message, source_module, resolved=False, resolution=None)
    lookup_error(error_message) -> dict | None
    get_summary() -> dict

All write functions are wrapped in try/except and never crash the pipeline.

Author: Maria (Orchestrator)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Storage paths ──────────────────────────────────────────────────────────────
_STORE_DIR  = Path(__file__).parent / "memory_store"
_STORE_FILE = _STORE_DIR / "memory_store.json"


# ── Internal helpers ───────────────────────────────────────────────────────────

def _load() -> dict:
    """
    Load the memory store from disk.

    Returns an empty store skeleton if the file does not exist or is corrupt.
    """
    if not _STORE_FILE.exists():
        return {"task_outcomes": [], "error_patterns": []}
    try:
        text = _STORE_FILE.read_text(encoding="utf-8")
        data = json.loads(text)
        # Ensure both lists exist even in legacy files
        data.setdefault("task_outcomes", [])
        data.setdefault("error_patterns", [])
        return data
    except Exception:
        return {"task_outcomes": [], "error_patterns": []}


def _save(store: dict) -> None:
    """Persist the memory store to disk, creating the directory if needed."""
    _STORE_DIR.mkdir(parents=True, exist_ok=True)
    _STORE_FILE.write_text(
        json.dumps(store, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _compute_fingerprint(error_message: str) -> str:
    """
    Compute a compact fingerprint from an error message.

    Strategy:
      1. Look for a Python exception class name (e.g. ``ModuleNotFoundError``).
      2. For ``ModuleNotFoundError`` append the missing module name.
      3. For other errors, return just the exception class name.
      4. Fallback: first 50 characters of the message.

    Args:
        error_message: The raw error/stderr text from the pipeline.

    Returns:
        A short string like ``"ModuleNotFoundError:numpy"`` or ``"SyntaxError"``.
    """
    if not error_message:
        return "UnknownError"

    # Extract the first recognisable Python exception type
    match = re.search(r'\b(\w+(?:Error|Exception|Warning))\b', error_message)
    if not match:
        return error_message[:50].strip()

    error_type = match.group(1)

    # For ModuleNotFoundError, extract the module name for a more specific key
    if error_type == "ModuleNotFoundError":
        mod_match = re.search(
            r"No module named ['\"]([^'\"]+)['\"]", error_message
        )
        if mod_match:
            return f"{error_type}:{mod_match.group(1)}"

    # For ImportError with a module hint
    if error_type == "ImportError":
        mod_match = re.search(r"cannot import name '([^']+)'", error_message)
        if mod_match:
            return f"{error_type}:{mod_match.group(1)}"

    return error_type


def _now() -> str:
    """Return the current time as a human-readable string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── Public API ────────────────────────────────────────────────────────────────

def record_outcome(
    task_id: str,
    mode: str,
    prompt: str,
    status: str,
    total_time_s: float,
    handoff_retries: int = 0,
    debug_iterations: int = 0,
    error_type: Optional[str] = None,
    failed_stage: Optional[str] = None,
) -> None:
    """
    Append one task outcome to the memory store.

    Must be called at the end of ``run_generate()`` and ``run_debug()`` after
    the final result is known.  Wrapped in try/except — a store write failure
    never affects the pipeline.

    Args:
        task_id:          Unique identifier for the task (e.g. ``"gen_d6cd3a38"``).
        mode:             ``"generate"`` or ``"debug"``.
        prompt:           Original user prompt (stored as first 80 chars).
        status:           ``"success"`` or ``"failure"`` / ``"error"``.
        total_time_s:     Wall-clock seconds the task took.
        handoff_retries:  Number of generate→debug retry cycles.
        debug_iterations: Iterations the debugger ran before giving up.
        error_type:       Exception class name if the task failed, else None.
        failed_stage:     Stage name or step label where failure occurred.
    """
    try:
        store = _load()
        store["task_outcomes"].append({
            "task_id":          task_id,
            "timestamp":        _now(),
            "mode":             mode,
            "prompt_summary":   (prompt or "")[:80],
            "status":           status,
            "total_time_s":     round(float(total_time_s), 3),
            "handoff_retries":  handoff_retries,
            "debug_iterations": debug_iterations,
            "error_type":       error_type,
            "failed_stage":     failed_stage,
        })
        _save(store)
    except Exception:
        pass   # never crash the pipeline


def record_error(
    error_message: str,
    source_module: str,
    resolved: bool = False,
    resolution: Optional[str] = None,
) -> None:
    """
    Record or update an error pattern in the memory store.

    If the computed fingerprint already exists:
        - increment ``count``
        - update ``last_seen``
        - update ``resolved`` / ``resolution`` if the new call supplies them

    If it is new, append a fresh entry.

    Wrapped in try/except — never crashes the pipeline.

    Args:
        error_message: Raw error text (stderr, exception message, etc.).
        source_module: Which pipeline module reported it (``"debugging"``, etc.).
        resolved:      True if the caller knows a fix was applied.
        resolution:    Human-readable description of the fix (e.g. ``"pip install numpy"``).
    """
    try:
        fingerprint = _compute_fingerprint(error_message)
        now = _now()

        store = _load()
        for entry in store["error_patterns"]:
            if entry.get("error_fingerprint") == fingerprint:
                entry["count"]     = int(entry.get("count", 0)) + 1
                entry["last_seen"] = now
                if resolved:
                    entry["resolved"]   = True
                    entry["resolution"] = resolution
                _save(store)
                return

        # New fingerprint — append
        store["error_patterns"].append({
            "error_fingerprint": fingerprint,
            "source_module":     source_module,
            "first_seen":        now,
            "last_seen":         now,
            "count":             1,
            "resolved":          resolved,
            "resolution":        resolution,
        })
        _save(store)
    except Exception:
        pass   # never crash the pipeline


def lookup_error(error_message: str) -> Optional[dict]:
    """
    Return the stored error-pattern entry matching ``error_message``, or None.

    Used by the orchestrator to check whether an error has been seen before
    and whether a known resolution exists.

    Args:
        error_message: Raw error text to look up.

    Returns:
        The matching ``error_patterns`` dict, or None if not found.
    """
    try:
        fingerprint = _compute_fingerprint(error_message)
        store = _load()
        for entry in store["error_patterns"]:
            if entry.get("error_fingerprint") == fingerprint:
                return entry
        return None
    except Exception:
        return None


def get_summary() -> dict:
    """
    Return an aggregated summary of the memory store.

    Returns:
        A dict with::

            {
                "total_runs":    N,
                "success_rate":  0.87,
                "top_errors":    [ <top-3 entries by count> ]
            }

        ``success_rate`` is 0.0 when there are no runs recorded.
    """
    try:
        store = _load()
        outcomes = store.get("task_outcomes", [])
        total    = len(outcomes)
        if total == 0:
            success_rate = 0.0
        else:
            successes    = sum(1 for o in outcomes if o.get("status") == "success")
            success_rate = round(successes / total, 4)

        patterns   = store.get("error_patterns", [])
        top_errors = sorted(patterns, key=lambda e: e.get("count", 0), reverse=True)[:3]

        return {
            "total_runs":   total,
            "success_rate": success_rate,
            "top_errors":   top_errors,
        }
    except Exception:
        return {"total_runs": 0, "success_rate": 0.0, "top_errors": []}
