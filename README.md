# Phase 4 - Reactive Code Debugging Workflow

This implementation delivers the **Phase 4 deterministic error-classification loop** from the workflow diagram, focused on the missing-package path:

- Execute Python command in sandboxed process
- Capture stderr and parse traceback/error line
- Classify deterministic error types
- Apply policy gates (confidence + idempotency)
- Plan and auto-run safe corrective actions
- Re-run command until success or max iterations
- Success requires both `exit_code == 0` and empty `stderr`
- If deterministic remediation cannot continue, automatically escalate to local LLM fallback

## Scope implemented

- Deterministic classifier supports:
  - `ModuleNotFoundError`
  - `ImportError` with `No module named ...`
  - `SyntaxError`, `IndentationError`
  - `FileNotFoundError`
- Deterministic corrective actions now cover missing modules and indentation normalization.
- `FileNotFoundError` is denied by default (no auto-create unless explicit allowlist policy).

## Deterministic corrective branches implemented

- `ModuleNotFoundError` / `ImportError` (missing module):
  - Action: `python -m pip install <module>`
- `SyntaxError` / `IndentationError` with parseable file + line:
  - Action: normalize indentation on the failing line (tabs to spaces, whitespace normalization)
  - Validation: `py_compile` on touched file; rollback on failure
- `FileNotFoundError` with parseable path:
  - Default action: deny auto-remediation (prevents unsafe file fabrication)
  - Optional action: create missing file only when path is explicitly allowlisted

## Deterministic safety controls

- Per-rule confidence thresholds (`RuleId`-based)
- Idempotency policy blocks repeated `(error fingerprint, action fingerprint)` loops
- Persistent action journal in `.phase4/action_journal.jsonl`
- Workspace-bounded path resolution for file actions

## Shared local model runtime

- Phase 4 and Phase 5 share one local Ollama runtime client instance
- Logical debug session:
  - `phase4_debug_session`
- Concurrency is controlled with an in-process semaphore
- Requests use retry with backoff and optional runtime health checks

## LLM fallback behavior

- Deterministic-first strategy is preserved
- LLM fallback is invoked only after deterministic terminal reasons, such as:
  - confidence gate denial
  - no deterministic action available
  - repeated action blocked by idempotency
  - deterministic corrective action execution failure
- Deterministic actions remain template-based:
  - `pip_install`
  - `normalize_indentation`
  - `replace_line`
- After deterministic terminal failure, fallback handoff is unrestricted for this phase:
  - LLM may propose arbitrary shell commands
  - LLM may propose arbitrary file writes
  - Guardrails for fallback are intentionally out of scope in this slice and are planned for a later microservice integration

## Project structure

- `src/phase4/domain`: models and interfaces
- `src/phase4/parsing`: stderr parser
- `src/phase4/classifier`: deterministic classifier
- `src/phase4/actions`: action planner and guarded executor
- `src/phase4/runtime`: subprocess execution adapter
- `src/phase4/llm`: local LLM provider for fallback actions
- `src/phase4/app`: shared composition service for bridge/debug mode and runtime reuse
- `src/phase4/workflow`: reactive loop orchestrator
- `demo/yfinance_missing_demo.py`: end-to-end demo using isolated venv
- `tests/unit`: parser + classifier/planner tests
- `tests/integration`: workflow test with fake engine

## Run tests

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
```

## Run yfinance missing-package demo

```powershell
py -3 demo/yfinance_missing_demo.py
```

Demo behavior:
1. Creates an isolated temporary venv
2. Runs `import yfinance` in that venv (first run should fail)
3. Classifier detects missing module and plans `pip install yfinance`
4. Applies fix and re-runs import
5. Prints JSON summary with attempts, decision path, and outcome
6. Writes deterministic journal entries to `.phase4/action_journal.jsonl`

## Phase 4 bridge entrypoint

Use this bridge to debug a Python file produced by any upstream service:

```powershell
py -3 scripts/phase4_bridge.py <generated_file.py>
```

Optional runtime flags:

```powershell
py -3 scripts/phase4_bridge.py <generated_file.py> --ollama-url http://localhost:11434 --ollama-model llama3.2 --check-runtime
```

## Phase 5 standalone debug mode

Run standalone reactive debugger on any target file:

```powershell
py -3 ESIBaiAgent.py --fix <target_file.py>
```

Optional runtime flags:

```powershell
py -3 ESIBaiAgent.py --fix <target_file.py> --ollama-url http://localhost:11434 --ollama-model llama3.2 --check-runtime
```
