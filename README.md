# Phase 4/5 - Reactive Debug Workflow

This implementation delivers a deterministic-first remediation loop for Python execution failures, with optional unrestricted LLM fallback when deterministic remediation reaches a terminal state.

## Behavior contract

1. Run target command and parse stderr.
2. Classify deterministic Python error types.
3. Apply confidence and idempotency policy gates.
4. Execute deterministic corrective action when available.
5. If deterministic remediation cannot continue (for example confidence deny, no action, repeated action, or deterministic action failure), optionally hand off to unrestricted LLM fallback.
6. Re-run command until success or max iterations.

Success is considered achieved when the command exits with code `0` and stderr is empty.

## Deterministic remediation scope

- Supported deterministic classes:
  - `ModuleNotFoundError`
  - `ImportError` containing `No module named ...`
  - `SyntaxError`
  - `IndentationError`
  - `FileNotFoundError`
- Supported deterministic actions:
  - `python -m pip install <module>`
  - indentation normalization with compile validation + rollback
  - optional allowlisted missing-file creation

## LLM fallback scope

When enabled, fallback accepts unrestricted plan payloads:

- `commands`: arbitrary shell command argv lists or shell strings
- `file_writes`: arbitrary file path + full content writes

Guardrails integration follows the shared policy contract from [Guardrails_Integration_Guide.md](Guardrails_Integration_Guide.md):

- Deterministic path bypasses guardrails (trusted pre-approved actions).
- Probabilistic path must call guardrails for every LLM-proposed command before execution.
- Only `PASS` commands are executed; `REJECT` and `BLOCK` stop fallback command execution.

The guardrails engine used by fallback commands is loaded from [FYP-guardrails-module/guardrails_engine.py](FYP-guardrails-module/guardrails_engine.py) with rules from [FYP-guardrails-module/guardrails_config.yaml](FYP-guardrails-module/guardrails_config.yaml).

Fallback is recorded as `llm_unrestricted_plan` in the action journal.

Guardrail hardening for unrestricted fallback is intentionally out of scope for this Phase 4/5 slice.

## Runtime and journaling

- Shared local Ollama runtime client/session manager for fallback provider calls
- Persistent JSONL journal at `.phase4/action_journal.jsonl`

## Entrypoints

- Phase 4 bridge:

```powershell
py -3 scripts/phase4_bridge.py <generated_file.py> --python <python_executable>
```

- Phase 5 debug mode:

```powershell
py -3 ESIBaiAgent.py --fix <target_file.py> --python <python_executable>
```

Both entrypoints emit JSON including `llm_fallback_used`.

## Run tests

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
```
