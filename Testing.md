# Testing Guide

**Project:** FYP 26/21 — ESIB AI Coding Agent  


---

## Table of Contents

1. [Philosophy](#1-philosophy)
2. [Architecture](#2-architecture)
3. [Test Inventory](#3-test-inventory)
   - [Unit Tests](#31-unit-tests)
   - [Integration Tests](#32-integration-tests)
   - [System Tests](#33-system-tests)
4. [Running the Tests](#4-running-the-tests)
5. [Coverage](#5-coverage)
6. [Static Analysis](#6-static-analysis)
7. [CI Pipeline](#7-ci-pipeline)
8. [Known Limitations](#8-known-limitations)
9. [Adding New Tests](#9-adding-new-tests)

---

## 1. Philosophy

Two principles drive every decision in this test suite.

**Tests run on the host, not inside the Docker sandbox.**  
The Docker sandbox (`agent-sandbox` image) exists to safely execute *untrusted, LLM-generated code* at runtime. The test suite verifies *your own trusted source code*. Mixing these two concerns would mean the sandbox's `--read-only` filesystem, `--network none`, and `--no-new-privileges` flags actively block the things tests need to do: import modules, write to temp directories, patch internal functions, and collect coverage. Docker appears in tests only at the system level, where `DockerExecutor` is treated as a black box and its isolation guarantees are verified by actually running containers.

**No LLM, no Docker required for the vast majority of tests.**  
289 of the 309 tests — the entire unit and integration layers — run in under 1 second with zero external services. This means the test suite can run in CI, on a teammate's laptop, or during development without a running Ollama instance or Docker daemon.

---

## 2. Architecture

```
tests/
├── conftest.py                          # Shared fixtures (workspace, schema builders, venv stub)
├── unit/                                # Single-module isolation — no I/O except filesystem
│   ├── test_handoff_validator.py        # V1–V8 checks on HandoffValidator
│   ├── test_environment_preparer.py     # Schema A → Schema B conversion branches
│   ├── test_memory_store.py             # Error fingerprinting, dedup, summary arithmetic
│   ├── test_docker_executor_pure.py     # Package regex, ExecutionResult, hardening constants
│   ├── test_agent_logger.py             # JSONL output, never-crash guarantee, event constants
│   └── test_guardrails_engine.py        # Command validation, PASS/REJECT/BLOCK verdicts
├── integration/                         # Multi-module wiring — no LLM, no Docker
│   ├── test_process_handoff.py          # process_handoff(): Schema A → Schema B end-to-end
│   ├── test_orchestrator_logic.py       # Termination rules, run_debug(), memory integration
│   └── test_guardrails_integration.py   # Guardrails command validation across contexts
└── system/                              # End-to-end — requires Docker and/or Ollama
    ├── test_cli_fix_mode.py             # --fix CLI mode via subprocess
    ├── test_cli_generate_mode.py        # --generate CLI mode via subprocess
    └── test_docker_sandbox.py           # Docker isolation and security verification
```

**Shared configuration:**

| File | Purpose |
|------|---------|
| `pytest.ini` | Test discovery paths, marker registration, default flags |
| `requirements-test.txt` | All testing dependencies |
| `.github/workflows/test.yml` | CI: automated pipeline on every push to `main` |

---

## 3. Test Inventory

### Summary

| Layer | Files | Tests | External services required |
|-------|-------|-------|---------------------------|
| Unit | 6 | 228 | None |
| Integration | 3 | 61 | None |
| System | 3 | 20 | Docker (sandbox tests), Ollama (LLM tests only) |
| **Total** | **12** | **309** | — |

---

### 3.1 Unit Tests

Each file targets one source module in complete isolation. External dependencies (LLM calls, Docker, network) are replaced with `tmp_path` fixtures and `unittest.mock.patch`. All 228 unit tests run with no external services.

---

#### `test_handoff_validator.py`

**Source module:** `orchestrator_handoff.py` → `HandoffValidator`

`HandoffValidator` implements eight sequential validation checks (V1–V8) on the Schema A payload that travels from Joe's generation module to Raymond's debugging module. This is the most important unit test file in the suite because it covers the architectural contribution that distinguishes the project: the formal handoff protocol with feedback-enriched retry.

| Class | Check | What is verified |
|-------|-------|-----------------|
| `TestV1RequiredFields` | V1 | All 7 top-level required fields; all 4 required metadata sub-fields; empty payload; error message names the missing field |
| `TestV2GenerationStatus` | V2 | `"success"` passes; `"failure"`, `"error"`, `"pending"`, `""`, `"SUCCESS"`, `"  success  "` all raise `GenerationFailedError`; error message includes the actual bad value |
| `TestV3ScriptExists` | V3 | Existing file passes; non-existent path raises `FileValidationError`; directory path raises `FileValidationError` |
| `TestV4WorkspaceExists` | V4 | Existing directory passes; non-existent path raises; file path used as directory raises |
| `TestV5PathSecurity` | V5 | Valid confined path passes; `..` traversal raises `PathSecurityError`; script outside workspace raises; absolute escape to `/etc` raises |
| `TestV6VenvValidity` | V6 | `venv_created=False` skips silently; valid venv layout passes; missing `venv_path` raises `MissingFieldError`; non-existent venv dir raises `FileValidationError`; venv dir with no Python binary raises |
| `TestV7RequirementsConsistency` | V7 | Non-empty requirements passes silently; empty requirements does NOT raise (warning only); warning is logged |
| `TestV8InteractiveInput` | V8 | `input()`, `sys.stdin.read`, `sys.stdin.readline`, `getpass.getpass` each trigger a WARNING; none raises; clean code produces no warning; non-existent script skips gracefully |
| `TestFullValidatePipeline` | V1–V8 | Full `validate()` call passes on valid payload; V1/V2/V3 failures surface correctly through the full pipeline |

---

#### `test_environment_preparer.py`

**Source module:** `orchestrator_handoff.py` → `EnvironmentPreparer`

`EnvironmentPreparer` has two branches: a no-venv path (use `sys.executable`, populate `pending_installs`) and a venv path (use venv Python, set `VIRTUAL_ENV` and `PATH`). Both branches are platform-aware (`win32` vs. POSIX).

| Class | What is verified |
|-------|-----------------|
| `TestSchemaBStructure` | All required Schema B keys present; `task_id`, `script_path`, `working_dir` match Schema A |
| `TestNoVenvBranch` | `python_executable` is `sys.executable`; requirements become `pending_installs`; empty requirements produces no `pending_installs` key; `env_vars` is empty dict |
| `TestVenvBranch` | `python_executable` is inside venv dir; `VIRTUAL_ENV` in `env_vars`; `PATH` in `env_vars`; venv bin dir precedes system PATH; correct binary name for platform (`python` vs `python.exe`) |
| `TestOriginalPromptForwarding` | `original_prompt` forwarded when present; absent from Schema B when absent from Schema A |

---

#### `test_memory_store.py`

**Source module:** `memory_store.py`

`memory_store.py` is pure Python + JSON with no external dependencies beyond the filesystem. Every test redirects `_STORE_DIR` and `_STORE_FILE` to `tmp_path` via `monkeypatch` so the real `memory_store.json` on disk is never touched.

| Class | What is verified |
|-------|-----------------|
| `TestComputeFingerprint` | `ModuleNotFoundError:numpy` format; double-quote variant; `ImportError:symbol` format; generic error class names; empty string → `"UnknownError"`; no-match fallback truncated to 50 chars |
| `TestRecordOutcome` | File created on first call; all required fields written; prompt truncated to 80 chars; multiple calls accumulate; `total_time_s` rounded to 3 decimal places; corrupt store does not raise |
| `TestRecordError` | New fingerprint creates entry; same fingerprint increments `count`; different fingerprints create separate entries; `resolved` and `resolution` updated on repeat; `last_seen` updated; corrupt store does not raise |
| `TestLookupError` | Known error found with correct fields; unknown error returns `None`; empty store returns `None`; corrupt store returns `None` |
| `TestGetSummary` | Empty store returns zero totals; all-success → `1.0`; all-failure → `0.0`; mixed → correct ratio; `top_errors` sorted by count descending; never more than 3 entries; corrupt store returns safe default |
| `TestLoadResilience` | Missing file returns skeleton; corrupt JSON returns skeleton; empty file returns skeleton; legacy file without `error_patterns` gets it added |

---

#### `test_docker_executor_pure.py`

**Source module:** `docker_executor.py`

These tests cover only the logic that can be verified without a running Docker daemon: the `_SAFE_PACKAGE_RE` package-name regex, the `ExecutionResult` dataclass, and the hardening constants on `DockerExecutor`. Runtime container tests live in `tests/system/test_docker_sandbox.py`.

| Class | What is verified |
|-------|-----------------|
| `TestSafePackageRegexValid` | Plain names, version equality, version ranges, extras notation (`requests[security]`), tilde-equal, underscores, dots, single-char names all accepted |
| `TestSafePackageRegexInvalid` | Shell injection (`; rm -rf /`, `&&`, `\|`, `$()`, backticks, `>`), spaces, empty string, path traversal, newlines, null bytes all rejected |
| `TestSafePackageRegexValid::test_known_regex_limitation_comma_version` | Documents that comma-separated version constraints (`numpy>=1.21,<2.0`) are currently rejected — a known gap |
| `TestExecutionResult` | All fields accessible; `error_type` defaults to `None`; `error_type` can be set; non-zero return code is not success |
| `TestDockerExecutorConstants` | `MEMORY_LIMIT == "512m"`; `CPU_LIMIT == "1"`; `PID_LIMIT == "100"`; `IMAGE_NAME == "agent-sandbox"`; `DEFAULT_TIMEOUT < MAX_TIMEOUT`; `MAX_TIMEOUT == 300` |

> The constants test is a deliberate safety net: accidentally changing `MEMORY_LIMIT` from `"512m"` to `"5120m"` would silently weaken sandbox isolation. The test makes any such change a conscious, CI-failing decision.

---

#### `test_agent_logger.py`

**Source module:** `agent_logger.py`

Agent logger uses module-level global state (`_jsonl_path`, `_log_fh`, `_orig_stdout`, `_initialized`). An `autouse` fixture calls `close_logger()` before and after every test to prevent state leakage between tests.

| Class | What is verified |
|-------|-----------------|
| `TestInitLogger` | Log directory created; returns `Path` with `.log` suffix; session log file exists; `_jsonl_path` set in log dir; filename is `agent_events.jsonl`; `_initialized` flag set; existing directory does not raise |
| `TestLogFunction` | JSONL entry created; all required keys present (`timestamp`, `source`, `level`, `event_type`, `payload`); source field correct; event type correct; payload preserved; default level is `INFO`; custom level works; multiple calls append multiple lines; `_jsonl_path = None` → silent no-op; unserializable payload does not raise |
| `TestCloseLogger` | `sys.stdout` restored after close; `_initialized` set to `False`; calling before `init_logger` does not raise |
| `TestGetLogger` | Returns `logging.Logger` instance; name matches; works before `init_logger` |
| `TestEventTypeConstants` | All 11 event-type constants defined and are non-empty strings |

---

#### `test_guardrails_engine.py`

**Source module:** `guardrails_engine.py` → `GuardrailsEngine`  
**Original author:** Elise Nassar (Security & Guardrails, Module 7)

`GuardrailsEngine` validates every command the LLM proposes before it reaches the Docker executor. It is the primary defence against shell injection, path traversal, and privilege escalation. Originally written by Elise at the repo root and migrated into `tests/unit/` so it is discovered automatically by pytest and included in CI.

The `setUpClass` fixture creates a real temporary workspace directory and a patched copy of `guardrails_config.yaml` that redirects `workspace_root` to that temp directory. Cleanup is handled by `tearDownClass`.

| Class | What is verified |
|-------|-----------------|
| `TestTokenOrderReportExamples` | Representative examples from the Token Order Validation Report: `python main.py` passes; `pip numpy install` rejects (wrong token order); `-m python ...` rejects (flag as executable); `rm -rf /` rejects; `$1` blocks; `;` chain rejects; `find -exec rm` rejects |
| `TestCommandTemplatesPass` | Every whitelisted command template resolves to its correct `command_key`: `python_run_script`, `python_pip_install`, `python_pip_show`, `python_ruff_check`, `pwd`, `ls`, `cat`, `head`, `tail`, `wc`, `diff`, `file_cmd`, `stat`, `grep`, `grep_recursive`, `find`, `mkdir`, `cp`, `mv`, `rm` |
| `TestRejections` | `curl`, `wget`, `sudo`, `ssh` rejected; pipe `\|`, `&&`, `>`, backtick, `$()` rejected; `rm -r/-f/--recursive` rejected; `find -delete` rejected; `python -c` rejected; `../` traversal rejected with rule `PATH-02`; path outside workspace rejected with rule `PATH-01`; `find -maxdepth 10` rejected as out of bounds; extra tokens rejected; empty command rejected; non-`.py` file to python rejected; injection in pip package name rejected |
| `TestBlocks` | `$1`, `$*`, `$@`, `$0`, `$9` all produce `BLOCK` status (variable expansion detected before whitelist matching) |
| `TestCallerService` | Same command produces identical `status` and `command_key` for both `"generation"` and `"debugging"` callers — the engine is caller-neutral by design |
| `TestResourceLimits` | `resource_limits` accessor returns `max_memory_mb == 2048` and `execution_timeout_seconds == 60` |

---

### 3.2 Integration Tests

Integration tests wire two or more real modules together with real filesystem I/O. External dependencies (LLM, Docker, Ollama) are replaced with `unittest.mock` stubs. All 61 integration tests run with no external services.

---

#### `test_process_handoff.py`

**Source modules:** `orchestrator_handoff.py` → `process_handoff()` (chains `HandoffValidator` + `EnvironmentPreparer`)

`process_handoff()` is the exact interface boundary between Joe's generation module and Raymond's debugging module. A regression here breaks the entire pipeline regardless of which individual module is correct.

| Class | What is verified |
|-------|-----------------|
| `TestProcessHandoffHappyPath` | Returns dict; all Schema B required keys present; `script_path`, `working_dir`, `task_id` match Schema A; `python_executable` is non-empty string; no-venv uses `sys.executable`; requirements become `pending_installs`; empty requirements produces no key; `original_prompt` forwarded |
| `TestProcessHandoffWithVenv` | Venv Python inside venv dir; `VIRTUAL_ENV` in `env_vars` with correct value; venv bin precedes system in `PATH` |
| `TestProcessHandoffFailurePaths` | `MissingFieldError` on missing `task_id`; `GenerationFailedError` on bad status; `FileValidationError` or `PathSecurityError` on non-existent script; `..` traversal raises security or file error; all validation errors catchable as `HandoffValidationError` |
| `TestSchemaBContract` | `script_path` is absolute string; `working_dir` is string; `task_id` is string; `python_executable` points to a real file on disk; `env_vars` is a dict |

---

#### `test_orchestrator_logic.py`

**Source modules:** `orchestrator.py` → `Orchestrator`, `SubprocessExecutor`, `_ExecutionResult`

These tests verify the Orchestrator's own logic independently of the LLM and Docker. `CodeDebugger` and `_memory_store` are replaced with `MagicMock` stubs controlled by each test.

| Class | What is verified |
|-------|-----------------|
| `TestTerminationConstants` | `MAX_DEBUG_ITERATIONS == 10`; `MAX_SAME_ERROR_COUNT == 3`; `MAX_HANDOFF_RETRIES == 2`; `SESSION_TIMEOUT_SECONDS == 1800` |
| `TestSubprocessExecutor` | Hello-world exits zero; syntax error exits non-zero; all `ExecutionResult` fields accessible; stdout captured; stderr captured; timeout sets `timed_out = True` and `return_code = -1`; empty packages behaves like `execute()` |
| `TestExecutionResultMimic` | All attributes accessible; `error_type` can be set |
| `TestRunDebugMode` | Missing script returns `status == "error"`; valid script with mocked debugger returns `success`; Schema B passed to debugger has correct keys and absolute path; result contains `task_id` starting with `"dbg_"`; `DEBUGGING_AVAILABLE=False` returns `status == "failure"` |
| `TestSessionTimeout` | Elapsed > 30 min causes `_run_debug_loop` to return `status == "failure"` without calling `CodeDebugger` at all |
| `TestMemoryStoreIntegration` | `record_outcome` called once after successful debug with correct `mode` and `status`; called after failed debug with non-success status; `record_outcome` raising `RuntimeError` does not crash the pipeline |

---

#### `test_guardrails_integration.py`

**Source modules:** `guardrails_engine.py` wired into the broader command validation context

These tests verify guardrails behaviour when invoked across different calling contexts — specifically that command chaining, variable expansion, and path traversal are blocked consistently regardless of caller.

| Class | What is verified |
|-------|-----------------|
| `TestGuardrailsIntegration` | Command chaining (`cmd1; cmd2`) rejected; variable expansion (`$1`) blocked; `../` path traversal rejected with correct rule ID |

---

### 3.3 System Tests

System tests invoke real external services — Docker and/or Ollama. They verify end-to-end behaviour that cannot be simulated with mocks. All 20 system tests require a running Docker daemon; the LLM-dependent subset additionally requires Ollama with `qwen3:8b`.

---

#### `test_docker_sandbox.py`

**Purpose:** Verify that the Docker executor's security flags produce the correct runtime isolation. Tests deliberately attempt to break the sandbox — a pass means the containment held.

| Class | What is verified |
|-------|-----------------|
| `TestDockerSandboxIsolation` | No network access; read-only root filesystem; memory limited to 512 MB; PID limit enforced; CPU limited to 1 core; disk write limit enforced |
| `TestDockerSecurityVerification` | Container runs as non-root UID 1000; cannot resolve external hostnames; cannot write to `/`; cannot `chown` files (capabilities dropped); cannot allocate 1 GB; cannot spawn unlimited processes |

---

#### `test_cli_fix_mode.py`

**Source:** `ESIB_AiCodingAgent.py --fix` invoked via `subprocess.run`

| Class | Requires Ollama | What is verified |
|-------|----------------|-----------------|
| `TestCLIAvailability` | No | CLI script exists; `--help` exits zero; output mentions `generate` and `fix`; non-existent script exits non-zero |
| `TestFixModeWorkingScript` | No | Working script passed to `--fix` exits zero; output contains success indicator |
| `TestFixModeBrokenScripts` | **Yes** | `NameError` fixed and exits zero; output contains `success`; `ZeroDivisionError` fixed and exits zero; `SyntaxError` fixed and exits zero; corrected script produces stdout |

---

#### `test_cli_generate_mode.py`

**Source:** `ESIB_AiCodingAgent.py --generate` invoked via `subprocess.run`

| Class | Requires Ollama | What is verified |
|-------|----------------|-----------------|
| `TestGenerateMode` | **Yes** | Simple hello-world script generated and executed successfully; Fibonacci sequence generator produced and verified |

---

## 4. Running the Tests

### Prerequisites

```bash
# Windows (inside activated virtual environment)
pip install -r requirements-test.txt

# Linux/macOS
pip3 install -r requirements-test.txt
```

### Fast tests — unit and integration only (no Docker, no Ollama, ~1 second)

```bash
# Windows
python -m pytest tests/unit tests/integration -v

# Linux/macOS
pytest tests/unit tests/integration -v
```

### Run a single file, class, or test

```bash
# Single file
pytest tests/unit/test_handoff_validator.py -v

# Single class
pytest tests/unit/test_handoff_validator.py::TestV5PathSecurity -v

# Single test
pytest tests/unit/test_handoff_validator.py::TestV5PathSecurity::test_dotdot_in_script_path_raises -v
```

### By marker

```bash
# Only unit tests
pytest -m unit -v

# Only integration tests
pytest -m integration -v

# Everything except system tests
pytest -m "not system" -v
```

### System tests — Docker sandbox (requires Docker, no Ollama)

```bash
pytest tests/system/test_docker_sandbox.py -v -m system
```

### System tests — CLI modes (requires Ollama with qwen3:8b)

```bash
# Full fix-mode tests
pytest tests/system/test_cli_fix_mode.py -v -m system

# CLI sanity checks only (no LLM needed)
pytest tests/system/test_cli_fix_mode.py -v -m "system and not slow"

# Generate mode tests
pytest tests/system/test_cli_generate_mode.py -v -m system
```

### Full suite (requires Docker + Ollama)

```bash
# Windows
python -m pytest tests/ -v

# Linux/macOS
pytest tests/ -v
```

### Stop on first failure

```bash
pytest tests/unit tests/integration -v -x
```

### Verbose with stdout visible (useful when debugging a single test)

```bash
pytest tests/unit/test_memory_store.py -v -s
```

---

## 5. Coverage

```bash
# Terminal report — shows uncovered lines
pytest tests/unit tests/integration \
  --cov=. \
  --cov-report=term-missing \
  --cov-omit="tests/*,venv/*,.venv/*"

# HTML report — open htmlcov/index.html in browser
pytest tests/unit tests/integration \
  --cov=. \
  --cov-report=html \
  --cov-omit="tests/*,venv/*,.venv/*"

# Enforce minimum threshold
pytest tests/unit tests/integration \
  --cov=. \
  --cov-fail-under=80 \
  --cov-omit="tests/*,venv/*,.venv/*"
```

**Coverage targets by module:**

| Module | Target | Priority | Notes |
|--------|--------|---------|-------|
| `orchestrator_handoff.py` | ≥ 90% | Critical | Novel architectural contribution |
| `memory_store.py` | ≥ 90% | High | Pure Python, fully testable |
| `guardrails_engine.py` | ≥ 85% | High | Security-critical path |
| `agent_logger.py` | ≥ 85% | High | Never-crash guarantee must be verified |
| `docker_executor.py` | ≥ 60% | Medium | Runtime Docker paths excluded from unit layer |
| `orchestrator.py` | ≥ 60% | Medium | LLM-dependent paths excluded |

> **On the 48% overall figure:** The project's overall coverage is 48%, which is excellent for a system where a significant portion of execution paths require a live LLM. The uncovered lines are concentrated in `generation.py` and `debugging.py` — the LLM interaction paths — exercised only during live system test runs.

---

## 6. Static Analysis

```bash
# Hard errors — syntax errors and undefined names (must be zero)
flake8 . --select=E9,F63,F7,F82 --exclude=venv,.venv,__pycache__

# Full style check — informational only
flake8 . --max-line-length=100 --exclude=venv,.venv,__pycache__

# Type checking
mypy . --ignore-missing-imports --exclude venv --exclude .venv
```

---

## 7. CI Pipeline

The CI workflow (`.github/workflows/test.yml`) runs automatically on every push to `main`. It is structured as two stages: a parallel fast-test matrix followed by specialised downstream jobs.

### Stage 1 — Fast Tests (parallel, Python matrix)

Three jobs run simultaneously across Python 3.10, 3.11, and 3.13:

```
1. Checkout repository
2. Set up Python (matrix: 3.10 / 3.11 / 3.13)
3. Install dependencies (requirements.txt + requirements-test.txt)
4. flake8 — hard errors only (E9, F63, F7, F82) — fails build if any found
5. flake8 — full style check — informational, exit-zero
6. pytest tests/unit tests/integration --cov  (289 tests, ~1 second)
7. Upload coverage report
```

All three matrix jobs run in parallel and complete in approximately 1 minute.

### Stage 2 — Specialised Jobs (run after Stage 1 passes)

| Job | Trigger | What it runs | Requires |
|-----|---------|-------------|---------|
| **Docker Security Tests** | Every push | `test_docker_sandbox.py` — 20 container isolation assertions | Docker |
| **Guardrails Integration Tests** | Every push | `test_guardrails_integration.py` — command validation contexts | None |
| **Generate Mode Tests** | Manual | `test_cli_generate_mode.py` — full LLM generation pipeline | Ollama |
| **Fix Mode Tests** | Manual | `test_cli_fix_mode.py` — full LLM debugging pipeline | Ollama |

Generate and Fix Mode tests use a manual trigger because they require a live Ollama instance with `qwen3:8b` loaded, which is not available in the standard GitHub Actions environment. They are triggered manually before significant releases and during jury preparation.

### Reading the CI dashboard

A green **Success** badge means all automated jobs passed: Fast Tests (×3) + Docker Security Tests + Guardrails Integration Tests. Generate and Fix Mode results appear separately when manually triggered and are shown in the same run summary.

---

## 8. Known Limitations

**Comma-separated version constraints in `_SAFE_PACKAGE_RE`**  
The package name regex in `docker_executor.py` does not support comma-separated version constraints such as `numpy>=1.21,<2.0`. These are valid pip specifications but are currently rejected, causing a `PackageInstallError` at runtime. The test `test_known_regex_limitation_comma_version` documents this explicitly. The security impact is low — rejection causes an install failure rather than a security bypass.

**LLM-dependent paths are not covered by automated CI tests**  
The generation pipeline (Stages 1–6 in `generation.py`) and the LLM-based fix strategies in `debugging.py` require a live Ollama connection and are not covered by the unit or integration layers. They are exercised only by the manually-triggered system tests and during normal agent operation.

**`TestFixModeBrokenScripts` and `TestGenerateMode` are non-deterministic**  
LLM output varies between runs. A script repaired in one run may hit the iteration limit in another if the model produces unexpected output. This is inherent to any LLM-based system. Run these tests multiple times before concluding a regression has occurred.

---

## 9. Adding New Tests

**File naming:** `tests/unit/test_<module_name>.py` or `tests/integration/test_<feature>.py`. Mirror the source module name exactly.

**Class naming:** `Test<ClassName>` or `Test<FeatureName>`. One class per logical concern.

**Fixture use:** Prefer the shared fixtures in `conftest.py` (`workspace`, `valid_schema_a`, `script_file`, `venv_stub`) over local temp directories. Add new shared fixtures to `conftest.py` when more than one test file needs them.

**Markers:** Always decorate with `@pytest.mark.unit`, `@pytest.mark.integration`, or `@pytest.mark.system`.

**Isolation:** Unit tests must not make real network calls, import the LLM client, or instantiate `DockerExecutor`. Use `unittest.mock.patch` to replace any such dependency.

**Parametrize instead of repeating:** When the same assertion applies to multiple inputs, use `@pytest.mark.parametrize`. Each case should be independently meaningful.

**Document known gaps:** If a test discovers a real limitation in the source code, add a dedicated test named with a `test_known_*` prefix. This prevents future developers from silently fixing the gap without updating the test suite.

---

*Last updated: April 30, 2026*