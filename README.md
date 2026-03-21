# Phase 4 - Reactive Code Debugging Workflow

This implementation delivers the **Phase 4 deterministic error-classification loop** from the workflow diagram, focused on the missing-package path:

- Execute Python command in sandboxed process
- Capture stderr and parse traceback/error line
- Classify deterministic error types
- Apply policy gates (confidence + idempotency)
- Plan and auto-run safe corrective actions
- Re-run command until success or max iterations

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

## Project structure

- `src/phase4/domain`: models and interfaces
- `src/phase4/parsing`: stderr parser
- `src/phase4/classifier`: deterministic classifier
- `src/phase4/actions`: action planner and guarded executor
- `src/phase4/runtime`: subprocess execution adapter
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
