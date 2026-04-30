"""
tests/unit/test_memory_store.py
================================
Unit tests for memory_store.py (Module 10 — Persistent Memory Store).

Strategy
--------
memory_store.py is pure Python + JSON filesystem I/O with no external
dependencies. This makes it ideal for fast, isolated unit testing.

We use monkeypatch to redirect the module's private _STORE_FILE and
_STORE_DIR paths to pytest's tmp_path, so tests never touch the real
memory_store.json on disk.

Covers
------
- _compute_fingerprint: all branching paths
- record_outcome: append, correct fields, truncation of prompt
- record_error: new entry, deduplication (count increment), resolved update
- lookup_error: found, not found
- get_summary: arithmetic, empty store, top-3 ordering
- _load resilience: missing file, corrupted JSON
- never-crash guarantee: write functions swallow all exceptions
"""

import json
import pytest
from pathlib import Path


# ── Redirect storage paths before importing the module ────────────────────────
# We patch at the module level so every function uses tmp_path.

@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """
    Redirect _STORE_DIR and _STORE_FILE to tmp_path for every test.
    autouse=True means this applies to every test in this file automatically.
    """
    import memory_store as ms
    store_dir  = tmp_path / "memory_store"
    store_file = store_dir / "memory_store.json"
    monkeypatch.setattr(ms, "_STORE_DIR",  store_dir)
    monkeypatch.setattr(ms, "_STORE_FILE", store_file)
    return store_file


# ═══════════════════════════════════════════════════════════════════════════════
# _compute_fingerprint
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestComputeFingerprint:
    """
    _compute_fingerprint is a private helper but it drives the dedup logic,
    so we test it directly via the module's internal namespace.
    """

    def _fp(self, message: str) -> str:
        import memory_store as ms
        return ms._compute_fingerprint(message)

    def test_module_not_found_with_module_name(self):
        msg = "ModuleNotFoundError: No module named 'numpy'"
        assert self._fp(msg) == "ModuleNotFoundError:numpy"

    def test_module_not_found_double_quotes(self):
        msg = 'ModuleNotFoundError: No module named "pandas"'
        assert self._fp(msg) == "ModuleNotFoundError:pandas"

    def test_import_error_with_symbol(self):
        msg = "ImportError: cannot import name 'DataFrame'"
        assert self._fp(msg) == "ImportError:DataFrame"

    def test_generic_error_returns_class_name(self):
        msg = "ZeroDivisionError: division by zero"
        assert self._fp(msg) == "ZeroDivisionError"

    def test_syntax_error_returns_class_name(self):
        msg = "SyntaxError: invalid syntax (line 5)"
        assert self._fp(msg) == "SyntaxError"

    def test_value_error_returns_class_name(self):
        msg = "ValueError: invalid literal for int() with base 10: 'abc'"
        assert self._fp(msg) == "ValueError"

    def test_empty_string_returns_unknown(self):
        assert self._fp("") == "UnknownError"

    def test_no_exception_class_falls_back_to_first_50_chars(self):
        msg = "something went terribly wrong with no class"
        result = self._fp(msg)
        assert result == msg[:50].strip()

    def test_long_fallback_is_truncated_to_50_chars(self):
        msg = "x" * 200   # no exception class in it
        result = self._fp(msg)
        assert len(result) <= 50


# ═══════════════════════════════════════════════════════════════════════════════
# record_outcome
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestRecordOutcome:

    def _load_store(self):
        import memory_store as ms
        return ms._load()

    def test_record_creates_file_if_missing(self, isolated_store):
        import memory_store as ms
        assert not isolated_store.exists()
        ms.record_outcome("t1", "generate", "prompt", "success", 1.5)
        assert isolated_store.exists()

    def test_record_appends_correct_fields(self, isolated_store):
        import memory_store as ms
        ms.record_outcome(
            task_id="t1",
            mode="generate",
            prompt="write a fibonacci function",
            status="success",
            total_time_s=12.345,
            handoff_retries=0,
            debug_iterations=2,
            error_type=None,
            failed_stage=None,
        )
        store = self._load_store()
        assert len(store["task_outcomes"]) == 1
        entry = store["task_outcomes"][0]
        assert entry["task_id"]          == "t1"
        assert entry["mode"]             == "generate"
        assert entry["status"]           == "success"
        assert entry["total_time_s"]     == 12.345
        assert entry["debug_iterations"] == 2
        assert entry["error_type"]       is None

    def test_prompt_truncated_to_80_chars(self, isolated_store):
        import memory_store as ms
        long_prompt = "A" * 200
        ms.record_outcome("t2", "generate", long_prompt, "success", 1.0)
        store = self._load_store()
        assert len(store["task_outcomes"][0]["prompt_summary"]) <= 80

    def test_multiple_outcomes_accumulate(self, isolated_store):
        import memory_store as ms
        ms.record_outcome("t1", "generate", "p1", "success", 1.0)
        ms.record_outcome("t2", "debug",    "p2", "failure", 2.0)
        ms.record_outcome("t3", "generate", "p3", "success", 0.5)
        store = self._load_store()
        assert len(store["task_outcomes"]) == 3

    def test_total_time_rounded_to_3_decimal_places(self, isolated_store):
        import memory_store as ms
        ms.record_outcome("t1", "generate", "p", "success", 1.123456789)
        store = self._load_store()
        total = store["task_outcomes"][0]["total_time_s"]
        assert total == round(1.123456789, 3)

    def test_record_outcome_never_raises_on_corrupt_store(
        self, isolated_store, monkeypatch
    ):
        """record_outcome must swallow exceptions — never crash the pipeline."""
        import memory_store as ms
        # Write garbage JSON to the store file
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("{bad json!!!", encoding="utf-8")
        # Must not raise
        ms.record_outcome("t1", "generate", "p", "success", 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# record_error + deduplication
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestRecordError:

    def _load_store(self):
        import memory_store as ms
        return ms._load()

    def test_new_error_creates_entry(self, isolated_store):
        import memory_store as ms
        ms.record_error("ModuleNotFoundError: No module named 'numpy'",
                        source_module="debugging")
        store = self._load_store()
        assert len(store["error_patterns"]) == 1
        entry = store["error_patterns"][0]
        assert entry["error_fingerprint"] == "ModuleNotFoundError:numpy"
        assert entry["count"]             == 1
        assert entry["source_module"]     == "debugging"
        assert entry["resolved"]          is False

    def test_repeated_error_increments_count(self, isolated_store):
        import memory_store as ms
        msg = "ModuleNotFoundError: No module named 'pandas'"
        ms.record_error(msg, "debugging")
        ms.record_error(msg, "debugging")
        ms.record_error(msg, "debugging")
        store = self._load_store()
        assert len(store["error_patterns"]) == 1
        assert store["error_patterns"][0]["count"] == 3

    def test_different_errors_create_separate_entries(self, isolated_store):
        import memory_store as ms
        ms.record_error("ModuleNotFoundError: No module named 'numpy'",
                        "debugging")
        ms.record_error("SyntaxError: invalid syntax", "generation")
        store = self._load_store()
        assert len(store["error_patterns"]) == 2

    def test_resolved_flag_updated_on_repeat(self, isolated_store):
        import memory_store as ms
        msg = "ModuleNotFoundError: No module named 'requests'"
        ms.record_error(msg, "debugging")
        ms.record_error(msg, "debugging",
                        resolved=True, resolution="pip install requests")
        store = self._load_store()
        entry = store["error_patterns"][0]
        assert entry["resolved"]   is True
        assert entry["resolution"] == "pip install requests"
        assert entry["count"]      == 2

    def test_last_seen_is_updated_on_repeat(self, isolated_store):
        import memory_store as ms
        import time
        msg = "ValueError: bad input"
        ms.record_error(msg, "orchestrator")
        time.sleep(0.05)   # ensure timestamps differ
        ms.record_error(msg, "orchestrator")
        store = self._load_store()
        entry = store["error_patterns"][0]
        assert entry["last_seen"] >= entry["first_seen"]

    def test_record_error_never_raises(self, isolated_store, monkeypatch):
        """record_error must swallow exceptions — never crash the pipeline."""
        import memory_store as ms
        # Corrupt the store so _load() returns garbage
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("NOT JSON", encoding="utf-8")
        # Must not raise
        ms.record_error("SyntaxError", "generation")


# ═══════════════════════════════════════════════════════════════════════════════
# lookup_error
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLookupError:

    def test_known_error_is_found(self, isolated_store):
        import memory_store as ms
        msg = "ModuleNotFoundError: No module named 'scipy'"
        ms.record_error(msg, "debugging",
                        resolved=True, resolution="pip install scipy")
        result = ms.lookup_error(msg)
        assert result is not None
        assert result["error_fingerprint"] == "ModuleNotFoundError:scipy"
        assert result["resolved"]          is True

    def test_unknown_error_returns_none(self, isolated_store):
        import memory_store as ms
        result = ms.lookup_error("ZeroDivisionError: division by zero")
        assert result is None

    def test_lookup_returns_none_on_empty_store(self, isolated_store):
        import memory_store as ms
        result = ms.lookup_error("SomeError: message")
        assert result is None

    def test_lookup_never_raises(self, isolated_store, monkeypatch):
        """lookup_error must return None (not raise) on a corrupt store."""
        import memory_store as ms
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("CORRUPT", encoding="utf-8")
        result = ms.lookup_error("anything")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# get_summary
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestGetSummary:

    def test_empty_store_returns_zero_totals(self, isolated_store):
        import memory_store as ms
        summary = ms.get_summary()
        assert summary["total_runs"]    == 0
        assert summary["success_rate"]  == 0.0
        assert summary["top_errors"]    == []

    def test_success_rate_all_success(self, isolated_store):
        import memory_store as ms
        ms.record_outcome("t1", "generate", "p", "success", 1.0)
        ms.record_outcome("t2", "generate", "p", "success", 1.0)
        summary = ms.get_summary()
        assert summary["total_runs"]   == 2
        assert summary["success_rate"] == 1.0

    def test_success_rate_all_failure(self, isolated_store):
        import memory_store as ms
        ms.record_outcome("t1", "generate", "p", "failure", 1.0)
        ms.record_outcome("t2", "generate", "p", "failure", 1.0)
        summary = ms.get_summary()
        assert summary["success_rate"] == 0.0

    def test_success_rate_mixed(self, isolated_store):
        """3 runs, 2 successes → 0.6667."""
        import memory_store as ms
        ms.record_outcome("t1", "generate", "p", "success", 1.0)
        ms.record_outcome("t2", "generate", "p", "success", 1.0)
        ms.record_outcome("t3", "generate", "p", "failure", 1.0)
        summary = ms.get_summary()
        assert summary["total_runs"]   == 3
        assert abs(summary["success_rate"] - 0.6667) < 0.001

    def test_top_errors_sorted_by_count(self, isolated_store):
        """top_errors must return entries sorted by count descending."""
        import memory_store as ms
        # Record numpy 3 times, scipy 1 time, pandas 5 times
        for _ in range(3):
            ms.record_error("ModuleNotFoundError: No module named 'numpy'",
                            "debugging")
        ms.record_error("ModuleNotFoundError: No module named 'scipy'",
                        "debugging")
        for _ in range(5):
            ms.record_error("ModuleNotFoundError: No module named 'pandas'",
                            "debugging")

        summary = ms.get_summary()
        counts = [e["count"] for e in summary["top_errors"]]
        assert counts == sorted(counts, reverse=True)

    def test_top_errors_limited_to_3(self, isolated_store):
        """top_errors must never return more than 3 entries."""
        import memory_store as ms
        for name in ["numpy", "pandas", "scipy", "matplotlib", "sklearn"]:
            ms.record_error(
                f"ModuleNotFoundError: No module named '{name}'", "debugging"
            )
        summary = ms.get_summary()
        assert len(summary["top_errors"]) <= 3

    def test_get_summary_never_raises_on_corrupt_store(
        self, isolated_store
    ):
        """get_summary must return a safe default on corrupt store."""
        import memory_store as ms
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("CORRUPT JSON", encoding="utf-8")
        summary = ms.get_summary()
        assert summary["total_runs"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _load resilience
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestLoadResilience:

    def test_load_returns_skeleton_when_file_missing(self, isolated_store):
        import memory_store as ms
        result = ms._load()
        assert result == {"task_outcomes": [], "error_patterns": []}

    def test_load_returns_skeleton_when_json_is_corrupt(self, isolated_store):
        import memory_store as ms
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("{not valid json", encoding="utf-8")
        result = ms._load()
        assert result == {"task_outcomes": [], "error_patterns": []}

    def test_load_returns_skeleton_on_empty_file(self, isolated_store):
        import memory_store as ms
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text("", encoding="utf-8")
        result = ms._load()
        assert result == {"task_outcomes": [], "error_patterns": []}

    def test_load_adds_missing_lists_to_legacy_store(self, isolated_store):
        """A store file with only task_outcomes should get error_patterns added."""
        import memory_store as ms
        isolated_store.parent.mkdir(parents=True, exist_ok=True)
        isolated_store.write_text(
            json.dumps({"task_outcomes": []}), encoding="utf-8"
        )
        result = ms._load()
        assert "error_patterns" in result
