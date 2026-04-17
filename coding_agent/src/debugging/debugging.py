"""
debugging.py - Debugging Service Adapter
========================================
Implements the complete debugging phase behind CodeDebugger.debug(schema_b)
using local in-file logic only.

This module preserves the orchestrator-facing contract while enforcing:
- Deterministic trusted fixes for known errors
- Explicit guardrails validation for probabilistic LLM-proposed commands
- Hybrid probabilistic flow (validated command + trusted in-file code rewrite)
"""

import ast
import io
import importlib.util
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import tokenize
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("debugging")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
MAX_DEBUG_ITERATIONS = int(os.environ.get("MAX_DEBUG_ITERATIONS", "10"))
DEBUG_TIMEOUT = int(os.environ.get("DEBUG_TIMEOUT", "30"))
LLM_FALLBACK_MAX_ATTEMPTS = int(os.environ.get("LLM_FALLBACK_MAX_ATTEMPTS", "2"))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


STRESS_ENABLED_DEFAULT = _env_flag("DEBUG_STRESS_ENABLED", False)
STRESS_REPEAT_DEFAULT = _env_int("DEBUG_STRESS_REPEAT", 5, 1, 200)
STRESS_PROFILE_DEFAULT = os.environ.get("DEBUG_STRESS_PROFILE", "medium").strip().lower() or "medium"
STRESS_SCENARIOS_DEFAULT = os.environ.get(
    "DEBUG_STRESS_SCENARIOS",
    "deterministic_module_install_fail,syntax_repeat,probabilistic_guardrails_reject,probabilistic_guardrails_block,probabilistic_guardrails_pass",
)
STRESS_LOG_DIR_DEFAULT = os.environ.get("DEBUG_STRESS_LOG_DIR", "logs/stress")
STRESS_LOG_FILE_DEFAULT = os.environ.get("DEBUG_STRESS_LOG_FILE", "stress_debugging_log.jsonl")

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------
FIX_GENERATION_PROMPT = """\
You are the fix-generation component of a reactive debugging agent.
You operate inside a containerized sandbox.

Return only a JSON object with this exact schema:
{
  "proposed_command": "<single whitelisted command>",
  "corrected_code": "<complete corrected python file>",
  "reasoning": "<one sentence>"
}

Rules:
1. proposed_command must be exactly one command and must be from this allowlist family:
   - python -V
   - python <script.py>
   - python -m py_compile <file.py>
   - python -m pip show <pkg>
   - python -m pip list
   - python -m pip install <pkg>
   - python -m ruff check <path>
   - pwd, ls, ls -la, cat <file>, head -n N <file>, tail -n N <file>
   - wc -l <file>, diff <file_a> <file_b>, file <path>
   - grep -n "<pattern>" <file>, grep -R -n "<pattern>" <path>
   - find <path> -maxdepth N -type f
   - mkdir -p <dir>, cp <src> <dst>, mv <src> <dst>, rm <file>
2. No command chaining and no shell metacharacters (; | && > >> || ` $( ${).
3. corrected_code must be full valid Python source, no markdown fences.
4. Keep fixes minimal and targeted to the current runtime error.
"""

# ---------------------------------------------------------------------------
# Guardrails integration (probabilistic path only)
# ---------------------------------------------------------------------------
_guardrails_engine = None


def _load_debug_guardrails() -> None:
    """Load GuardrailsEngine and config from expected project locations."""
    global _guardrails_engine

    here = os.path.dirname(os.path.abspath(__file__))
    guardrails_dir = os.path.abspath(os.path.join(here, "..", "guardrails"))

    search_import_dirs = [
        here,
        guardrails_dir,
    ]

    for import_dir in search_import_dirs:
        if os.path.isdir(import_dir) and import_dir not in sys.path:
            sys.path.insert(0, import_dir)

    GuardrailsEngine = None
    try:
        from guardrails_engine import GuardrailsEngine as _GuardrailsEngine  # type: ignore[import]
        GuardrailsEngine = _GuardrailsEngine
    except Exception:
        engine_path = os.path.join(guardrails_dir, "guardrails_engine.py")
        if os.path.isfile(engine_path):
            spec = importlib.util.spec_from_file_location("guardrails_engine", engine_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                GuardrailsEngine = getattr(module, "GuardrailsEngine", None)

    if GuardrailsEngine is None:
        logger.warning("[Debugging] guardrails engine unavailable")
        return

    cfg_candidates = [
        os.path.join(here, "guardrails_config.yaml"),
        os.path.join(guardrails_dir, "guardrails_config.yaml"),
        os.path.abspath(os.path.join(here, "..", "guardrails", "guardrails_config.yaml")),
    ]

    for cfg_path in cfg_candidates:
        if os.path.isfile(cfg_path):
            try:
                _guardrails_engine = GuardrailsEngine(cfg_path)
                logger.info("[Debugging] guardrails loaded: %s", cfg_path)
                return
            except Exception as exc:
                logger.warning("[Debugging] failed to initialize guardrails from %s: %s", cfg_path, exc)

    logger.warning("[Debugging] guardrails config not found")


_load_debug_guardrails()


class _SubprocessDebugger:
    """
    Local debugger loop.

    Deterministic path (trusted): internal hard-coded actions.
    Probabilistic path (untrusted): LLM proposes a command, command must pass
    guardrails, then corrected code may be applied via trusted internal write.
    """

    def __init__(
        self,
        python_exe: str = "python3",
        working_dir: str = ".",
        ollama_url: str = OLLAMA_URL,
        ollama_model: str = OLLAMA_MODEL,
        max_iterations: int = MAX_DEBUG_ITERATIONS,
        timeout: int = DEBUG_TIMEOUT,
        executor: Any = None,
        llm_fallback_max_attempts: int = LLM_FALLBACK_MAX_ATTEMPTS,
        suppress_no_fix_warning: bool = False,
    ) -> None:
        self.python_exe = python_exe
        self.working_dir = working_dir
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.executor = executor
        self.llm_fallback_max_attempts = llm_fallback_max_attempts
        self.suppress_no_fix_warning = suppress_no_fix_warning

    def run(self, script_path: str, pending_installs: Optional[list] = None) -> dict:
        pending = pending_installs or []
        for pkg in pending:
            self._pip_install(str(pkg))

        last_stderr = ""
        last_exit_code = 1
        last_error_signature = ""
        same_error_count = 0
        llm_fallback_used = False
        failure_reason = ""

        for iteration in range(1, self.max_iterations + 1):
            logger.info("[Debug iter %d/%d] Running %s", iteration, self.max_iterations, script_path)

            run_result = self._execute_script(script_path)
            last_exit_code = int(run_result["return_code"])
            last_stderr = run_result["stderr"]

            if run_result["return_code"] == 0:
                # Exit code 0 = success.  Stderr may contain library warnings
                # (e.g. DeprecationWarning, ResourceWarning) — these are NOT failures.
                # This matches the orchestrator's own decision at Step 3.
                if run_result["stderr"].strip():
                    logger.info(
                        "[Debug iter %d] Script exited cleanly (code 0) with "
                        "stderr warnings (not treated as failure):\n%s",
                        iteration, run_result["stderr"][:300]
                    )
                return self._success_result(
                    script_path=script_path,
                    iteration=iteration,
                    stdout=run_result["stdout"],
                    stderr=run_result["stderr"],
                    final_exit_code=0,
                    llm_fallback_used=llm_fallback_used,
                )

            error_type = self._classify_error(run_result["stderr"])
            error_signature = self._error_signature(run_result["stderr"], error_type)
            logger.info("[Debug iter %d] Error type: %s", iteration, error_type)

            if error_signature == last_error_signature:
                same_error_count += 1
                if same_error_count >= 3:
                    failure_reason = f"same-error-repeated:{error_type}"
                    return self._failure_result(
                        script_path=script_path,
                        iteration=iteration,
                        stderr=run_result["stderr"],
                        error_message=f"Same error repeated 3 times: {error_type}",
                        failure_reason=failure_reason,
                        final_exit_code=last_exit_code,
                        llm_fallback_used=llm_fallback_used,
                    )
            else:
                same_error_count = 1
                last_error_signature = error_signature

            deterministic = self._try_deterministic_fix(script_path, run_result["stderr"], error_type, iteration)
            if deterministic.get("terminal_result"):
                terminal = deterministic["terminal_result"]
                terminal["llm_fallback_used"] = llm_fallback_used
                return terminal
            if deterministic.get("applied"):
                failure_reason = str(deterministic.get("failure_reason", "deterministic-fix-applied"))
                continue
            if deterministic.get("failure_reason"):
                failure_reason = str(deterministic["failure_reason"])

            probabilistic = self._try_probabilistic_fix(
                script_path=script_path,
                stderr=run_result["stderr"],
                error_type=error_type,
            )

            if probabilistic.get("applied"):
                llm_fallback_used = True
                failure_reason = "probabilistic-fix-applied"
                continue

            if probabilistic.get("terminal_result"):
                terminal = probabilistic["terminal_result"]
                terminal["llm_fallback_used"] = llm_fallback_used
                return terminal

            if probabilistic.get("failure_reason"):
                failure_reason = str(probabilistic["failure_reason"])
            else:
                failure_reason = "no-fix-applied"

            if self.suppress_no_fix_warning:
                logger.info("[Debug iter %d] No fix applied (%s)", iteration, failure_reason)
            else:
                logger.warning("[Debug iter %d] No fix applied (%s)", iteration, failure_reason)

        return self._failure_result(
            script_path=script_path,
            iteration=self.max_iterations,
            stderr=last_stderr,
            error_message=f"Max iterations ({self.max_iterations}) reached",
            failure_reason=failure_reason or "max-iterations-reached",
            final_exit_code=last_exit_code,
            llm_fallback_used=llm_fallback_used,
        )

    def _try_deterministic_fix(self, script_path: str, stderr: str, error_type: str, iteration: int) -> Dict[str, Any]:
        if error_type != "ModuleNotFoundError":
            if error_type == "FileNotFoundError":
                return {"applied": False, "failure_reason": "deterministic-file-not-found"}
            if error_type == "SyntaxError":
                if self._is_non_utf8_syntax_error(stderr):
                    repaired_code = self._repair_non_utf8_source(script_path)
                    if repaired_code and self._apply_fix(script_path, repaired_code):
                        logger.info("[Deterministic] Normalized non-UTF-8 source encoding")
                        return {"applied": True, "failure_reason": "deterministic-encoding-normalized"}
                    return {"applied": False, "failure_reason": "deterministic-encoding-failed"}

                if not self._is_high_confidence_syntax_error(script_path):
                    logger.info("[Deterministic] SyntaxError deemed complex; escalating to probabilistic path")
                    return {"applied": False, "failure_reason": "deterministic-syntax-escalated"}
                repaired_code = self._repair_simple_syntax_error(script_path)
                if repaired_code and self._is_valid_python(repaired_code):
                    if self._apply_fix(script_path, repaired_code):
                        logger.info("[Deterministic] Applied local syntax repair")
                        return {"applied": True, "failure_reason": "deterministic-syntax-repair"}
                return {"applied": False, "failure_reason": "deterministic-syntax-error"}
            return {"applied": False}

        module_name = self._extract_module_name(stderr)
        if not module_name:
            return {"applied": False, "failure_reason": "module-name-not-found"}

        logger.info("[Deterministic] pip install %s", module_name)

        if self.executor and hasattr(self.executor, "execute_with_packages"):
            try:
                with open(script_path, "r", encoding="utf-8") as file_handle:
                    code = file_handle.read()
                exec_result = self.executor.execute_with_packages(code, [module_name])
                if getattr(exec_result, "return_code", 1) == 0:
                    fixed_script_path = self._save_fixed_script(script_path, code)
                    return {
                        "terminal_result": self._success_result(
                            script_path=script_path,
                            iteration=iteration,
                            stdout=getattr(exec_result, "stdout", ""),
                            stderr=getattr(exec_result, "stderr", ""),
                            final_exit_code=0,
                            llm_fallback_used=False,
                            extra={
                                "fixed_script_path": fixed_script_path,
                                "fix_method": f"Docker package install: {module_name}",
                            },
                        )
                    }
            except Exception as exc:
                logger.warning("[Docker] execute_with_packages fallback: %s", exc)

        if self._pip_install(module_name):
            return {"applied": True, "failure_reason": "deterministic-module-install"}

        return {"applied": False, "failure_reason": "module-install-failed"}

    def _try_probabilistic_fix(self, script_path: str, stderr: str, error_type: str) -> Dict[str, Any]:
        if error_type == "ModuleNotFoundError":
            return {"applied": False}

        feedback = ""
        last_reason = "probabilistic-fix-unavailable"

        for attempt in range(1, self.llm_fallback_max_attempts + 1):
            proposal = self._ask_llm_for_fix_plan(
                script_path=script_path,
                stderr=stderr,
                error_type=error_type,
                attempt=attempt,
                feedback=feedback,
            )

            if not proposal:
                feedback = "Return valid JSON with proposed_command and corrected_code."
                last_reason = "llm-invalid-proposal"
                continue

            proposed_command = str(proposal.get("proposed_command", "")).strip()
            corrected_code = str(proposal.get("corrected_code", "")).strip()
            proposed_command = self._normalize_probabilistic_command(proposed_command, script_path)

            if not proposed_command and corrected_code:
                proposed_command = self._default_syntax_check_command(script_path)

            if not proposed_command:
                feedback = "Missing proposed_command."
                last_reason = "llm-missing-command"
                continue

            validation = self._validate_probabilistic_command(proposed_command)
            status = str(validation.get("status", "REJECT")).upper()
            if status != "PASS":
                rule_id = str(validation.get("failing_rule_id") or "unknown-rule")
                reason = str(validation.get("reason") or "command-rejected")
                feedback = (
                    f"Guardrails {status}: {reason}. "
                    f"failing_rule_id={rule_id}. Propose a different allowed command."
                )
                last_reason = f"guardrails-{status.lower()}:{rule_id}"

                fallback_validation: Optional[Dict[str, Any]] = None
                if corrected_code:
                    fallback_command = self._default_syntax_check_command(script_path)
                    fallback_validation = self._validate_probabilistic_command(fallback_command)

                    if str(fallback_validation.get("status", "REJECT")).upper() != "PASS":
                        probe_command = self._default_probe_command()
                        probe_validation = self._validate_probabilistic_command(probe_command)
                        if str(probe_validation.get("status", "REJECT")).upper() == "PASS":
                            fallback_validation = probe_validation

                if not fallback_validation or str(fallback_validation.get("status", "REJECT")).upper() != "PASS":
                    continue

                validation = fallback_validation

            token_array = validation.get("token_array") or []
            if not isinstance(token_array, list) or not token_array:
                feedback = "Guardrails PASS returned empty token_array; choose a valid command."
                last_reason = "guardrails-empty-token-array"
                continue

            _ = self._execute_tokens([str(token) for token in token_array])

            cleaned_code = self._sanitize_llm_code(corrected_code)
            if not cleaned_code:
                feedback = "corrected_code is empty; return full Python file content."
                last_reason = "llm-empty-code"
                continue

            if not self._is_valid_python(cleaned_code):
                repaired_code = self._repair_source_text(cleaned_code)
                if repaired_code and self._is_valid_python(repaired_code):
                    cleaned_code = repaired_code
                else:
                    feedback = "corrected_code is invalid Python; return syntactically valid code."
                    last_reason = "llm-invalid-python"
                    continue

            if self._apply_fix(script_path, cleaned_code):
                logger.info("[Probabilistic] Applied guardrails-validated LLM fix")
                return {"applied": True}

            feedback = "Failed to write corrected_code to file; retry with complete output."
            last_reason = "llm-apply-failed"

        return {"applied": False, "failure_reason": last_reason}

    def _validate_probabilistic_command(self, command: str) -> Dict[str, Any]:
        if _guardrails_engine is None:
            return {
                "status": "REJECT",
                "reason": "guardrails engine unavailable",
                "failing_rule_id": "guardrails_unavailable",
                "token_array": [],
                "command_key": None,
            }

        try:
            return _guardrails_engine.validate(
                {
                    "caller_service": "debugging",
                    "raw_command": command,
                    "working_dir": self.working_dir,
                }
            )
        except Exception as exc:
            return {
                "status": "REJECT",
                "reason": f"guardrails validation exception: {exc}",
                "failing_rule_id": "guardrails_validation_exception",
                "token_array": [],
                "command_key": None,
            }

    def _ask_llm_for_fix_plan(
        self,
        script_path: str,
        stderr: str,
        error_type: str,
        attempt: int,
        feedback: str,
    ) -> Optional[Dict[str, Any]]:
        import urllib.error
        import urllib.request

        code = self._read_script_text(script_path)
        if code is None:
            logger.warning("Failed to read script for LLM prompt: %s", script_path)
            return None

        user_prompt = (
            f"attempt={attempt}\n"
            f"script_path={script_path}\n"
            f"error_type={error_type}\n"
            f"previous_feedback={feedback or 'none'}\n"
            f"=== CODE (truncated) ===\n{code[:5000]}\n\n"
            f"=== STDERR (truncated) ===\n{stderr[:2000]}\n"
        )

        payload = json.dumps(
            {
                "model": self.ollama_model,
                "messages": [
                    {"role": "system", "content": FIX_GENERATION_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 3072},
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read())
            content = str(data.get("message", {}).get("content", "")).strip()
            return self._parse_llm_json(content, script_path=script_path)
        except Exception as exc:
            logger.warning("LLM fallback failed: %s", exc)
            return None

    def _parse_llm_json(self, content: str, script_path: str = "") -> Optional[Dict[str, Any]]:
        if not content:
            return None

        candidates = [content]
        first_brace = content.find("{")
        last_brace = content.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidates.append(content[first_brace : last_brace + 1])

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    command = (
                        parsed.get("proposed_command")
                        or parsed.get("command")
                        or parsed.get("next_command")
                        or ""
                    )
                    corrected = (
                        parsed.get("corrected_code")
                        or parsed.get("fixed_code")
                        or parsed.get("code")
                        or ""
                    )
                    return {
                        "proposed_command": str(command).strip(),
                        "corrected_code": str(corrected),
                        "reasoning": str(parsed.get("reasoning", "")).strip(),
                    }
            except Exception:
                continue

        extracted_code = self._extract_code_from_response(content)
        if extracted_code:
            return {
                "proposed_command": self._default_syntax_check_command(script_path) if script_path else "python -m py_compile",
                "corrected_code": extracted_code,
                "reasoning": "extracted code from non-JSON LLM response",
            }

        return None

    def _extract_code_from_response(self, content: str) -> str:
        fence_match = re.search(r"(`{3,}|~{3,})(?:python)?\s*\n(.*?)\1", content, re.DOTALL | re.IGNORECASE)
        if fence_match:
            return fence_match.group(2).strip()

        stripped = content.strip()
        if not stripped:
            return ""

        if self._looks_like_python_code(stripped):
            return stripped

        return ""

    def _looks_like_python_code(self, content: str) -> bool:
        lowered = content.lower()
        signals = ["def ", "class ", "import ", "from ", "if __name__", "print(", ":\n"]
        return any(signal in lowered for signal in signals)

    def _execute_script(self, script_path: str) -> Dict[str, Any]:
        return self._execute_tokens([self.python_exe, script_path])

    def _execute_tokens(self, tokens: List[str]) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                tokens,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
            )
            return {
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"TimeoutError: Execution exceeded {self.timeout}s",
            }
        except Exception as exc:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(exc),
            }

    def _pip_install(self, package: str) -> bool:
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "install", package],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                logger.warning("pip install %s failed: %s", package, (result.stderr or "")[:200])
            return result.returncode == 0
        except Exception as exc:
            logger.warning("pip install %s exception: %s", package, exc)
            return False

    def _classify_error(self, stderr: str) -> str:
        match = re.search(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.]*Error)\b", stderr)
        if match:
            error_name = match.group(1)
            error_map = {
                "ModuleNotFoundError": "ModuleNotFoundError",
                "ImportError": "ModuleNotFoundError",
                "SyntaxError": "SyntaxError",
                "IndentationError": "SyntaxError",
                "FileNotFoundError": "FileNotFoundError",
                "NameError": "NameError",
                "TypeError": "TypeError",
                "TimeoutError": "TimeoutError",
            }
            return error_map.get(error_name, "OtherError")

        if "ModuleNotFoundError" in stderr or "ImportError" in stderr:
            return "ModuleNotFoundError"
        if "SyntaxError" in stderr or "IndentationError" in stderr:
            return "SyntaxError"
        if "FileNotFoundError" in stderr:
            return "FileNotFoundError"
        if "NameError" in stderr:
            return "NameError"
        if "TypeError" in stderr:
            return "TypeError"
        if "TimeoutError" in stderr:
            return "TimeoutError"
        return "OtherError"

    def _error_signature(self, stderr: str, error_type: str) -> str:
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        tail = lines[-1] if lines else ""
        return f"{error_type}:{tail[:200]}"

    def _extract_module_name(self, stderr: str) -> str:
        match = re.search(r"No module named ['\"]?([A-Za-z0-9_.-]+)['\"]?", stderr)
        if match:
            return match.group(1).split(".")[0]

        match = re.search(r"cannot import name .+ from '([^']+)'", stderr)
        if match:
            return match.group(1).split(".")[0]

        return ""

    def _sanitize_llm_code(self, code_text: str) -> str:
        lines = code_text.strip().splitlines()
        fence_line_pattern = re.compile(r"^\s*(`{3,}|~{3,}).*$")

        if lines and fence_line_pattern.match(lines[0]):
            lines = lines[1:]
        if lines and re.match(r"^\s*(`{3,}|~{3,})\s*$", lines[-1]):
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _repair_simple_syntax_error(self, script_path: str) -> str:
        source = self._read_script_text(script_path)
        if source is None:
            logger.warning("Failed to read script for syntax repair: %s", script_path)
            return ""

        try:
            ast.parse(source, filename=script_path)
            return ""
        except SyntaxError as exc:
            repaired_code = self._repair_syntax_source(source, int(exc.lineno or 0), str(exc.msg or ""), str(exc.text or ""))
            if repaired_code:
                return repaired_code
            return ""

    def _is_high_confidence_syntax_error(self, script_path: str) -> bool:
        source = self._read_script_text(script_path)
        if source is None:
            return False

        try:
            ast.parse(source, filename=script_path)
            return False
        except SyntaxError as exc:
            message = str(exc.msg or "").lower()
            if any(token in message for token in ("was never closed", "unexpected eof", "unmatched")):
                return True
            if "expected ':'" in message:
                return True

            line_no = int(exc.lineno or 0)
            lines = source.splitlines()
            if line_no <= 0 or line_no > len(lines):
                return False

            stripped = lines[line_no - 1].strip()
            if not stripped:
                return False

            if self._looks_like_simple_for_range_typo(stripped):
                return True

            if self._looks_like_simple_missing_colon(stripped, message):
                return True

            if self._looks_like_plain_text_noise_line(stripped, message):
                return True

            return False

    def _looks_like_simple_for_range_typo(self, stripped_line: str) -> bool:
        pattern_1 = re.match(
            r"^for\s+[A-Za-z_][A-Za-z0-9_]*\s+n\s+range\(\)\s*:?\s*$",
            stripped_line,
        )
        if pattern_1:
            return True

        pattern_2 = re.match(
            r"^for\s+[A-Za-z_][A-Za-z0-9_]*\s+range\([^)]*\)\s*:?\s*$",
            stripped_line,
        )
        return bool(pattern_2)

    def _looks_like_simple_missing_colon(self, stripped_line: str, error_message: str) -> bool:
        if "expected ':'" not in error_message:
            return False
        if stripped_line.endswith(":"):
            return False
        return bool(
            re.match(
                r"^(if\b|elif\b|else\b|for\b|while\b|def\b|class\b|try\b|except\b|finally\b|with\b)",
                stripped_line,
            )
        )

    def _looks_like_plain_text_noise_line(self, stripped_line: str, error_message: str) -> bool:
        if not stripped_line:
            return False

        if "unexpected indent" not in error_message and "invalid syntax" not in error_message:
            return False

        if stripped_line.startswith(("#", '"', "'")):
            return False

        if any(token in stripped_line for token in ("(", ")", "[", "]", "{", "}", "=", ":")):
            return False

        # Common LLM prose/header noise that can appear in generated scripts.
        if re.match(r"^[A-Za-z][A-Za-z0-9 ,.'-]{5,}$", stripped_line):
            return True

        return False

    def _default_syntax_check_command(self, script_path: str) -> str:
        normalized_path = Path(script_path).as_posix()
        return f'python -m py_compile "{normalized_path}"'

    def _default_probe_command(self) -> str:
        return "python -V"

    def _normalize_probabilistic_command(self, command: str, script_path: str) -> str:
        normalized_command = (command or "").strip()
        if not normalized_command:
            return normalized_command

        normalized_path = Path(script_path).as_posix()
        windows_path = str(Path(script_path))

        variants = {
            windows_path,
            windows_path.replace("\\", "\\\\"),
            windows_path.replace("\\", "/"),
            normalized_path,
        }

        for variant in variants:
            if variant and variant in normalized_command and f'"{normalized_path}"' not in normalized_command:
                normalized_command = normalized_command.replace(variant, f'"{normalized_path}"')

        ruff_match = re.match(r"^python\s+-m\s+ruff\s+check\s+(.+\.py)\s*$", normalized_command, re.IGNORECASE)
        if ruff_match:
            raw_target = ruff_match.group(1).strip().strip('"')
            if " " in raw_target:
                normalized_command = f'python -m ruff check "{raw_target.replace("\\", "/")}"'

        return normalized_command

    def _is_non_utf8_syntax_error(self, stderr: str) -> bool:
        lowered = stderr.lower()
        return "non-utf-8 code" in lowered and "no encoding declared" in lowered

    def _repair_non_utf8_source(self, script_path: str) -> str:
        try:
            raw_bytes = Path(script_path).read_bytes()
        except Exception as exc:
            logger.warning("Failed to read bytes for encoding repair: %s", exc)
            return ""

        decoded = None
        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                decoded = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            decoded = raw_bytes.decode("utf-8", errors="replace")

        normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
        return normalized

    def _read_script_text(self, script_path: str) -> Optional[str]:
        try:
            raw_bytes = Path(script_path).read_bytes()
        except Exception as exc:
            logger.warning("Failed to read script bytes: %s", exc)
            return None

        for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        return raw_bytes.decode("utf-8", errors="replace")

    def _repair_source_text(self, source: str) -> str:
        try:
            ast.parse(source)
            return source
        except SyntaxError as exc:
            repaired_code = self._repair_syntax_source(source, int(exc.lineno or 0), str(exc.msg or ""), str(exc.text or ""))
            return repaired_code or ""

    def _repair_syntax_source(self, source: str, line_no: int, error_message: str, error_text: str) -> str:
        base_repair = self._repair_unmatched_delimiters(source, line_no)
        if base_repair:
            return base_repair

        line_repair = self._repair_common_line_typos(source, line_no, error_message, error_text)
        if line_repair:
            return line_repair

        return ""

    def _repair_unmatched_delimiters(self, source: str, line_no: int) -> str:
        unmatched_openers = self._find_unmatched_openers(source)
        if not unmatched_openers:
            return ""

        closer_map = {"(": ")", "[": "]", "{": "}"}
        closing_text = "".join(closer_map.get(open_char, "") for open_char in reversed(unmatched_openers))
        if not closing_text:
            return ""

        lines = source.splitlines(keepends=True)
        if not lines:
            return ""

        target_index = min(max(line_no, 1), len(lines)) - 1
        if target_index < 0 or target_index >= len(lines):
            return ""

        target_line = lines[target_index]
        newline = ""
        if target_line.endswith("\r\n"):
            newline = "\r\n"
            line_body = target_line[:-2]
        elif target_line.endswith("\n"):
            newline = "\n"
            line_body = target_line[:-1]
        else:
            line_body = target_line

        comment_index = None
        try:
            for token in tokenize.generate_tokens(io.StringIO(line_body + "\n").readline):
                if token.type == tokenize.COMMENT:
                    comment_index = token.start[1]
                    break
        except (tokenize.TokenError, IndentationError):
            comment_index = None

        if comment_index is not None:
            repaired_line = line_body[:comment_index].rstrip() + closing_text + line_body[comment_index:] + newline
        else:
            repaired_line = line_body.rstrip() + closing_text + newline

        if repaired_line == target_line:
            return ""

        lines[target_index] = repaired_line
        repaired_source = "".join(lines)
        try:
            ast.parse(repaired_source)
            return repaired_source
        except SyntaxError:
            return ""

    def _repair_common_line_typos(self, source: str, line_no: int, error_message: str, error_text: str) -> str:
        if line_no <= 0:
            return ""

        lines = source.splitlines(keepends=True)
        if not lines:
            return ""

        target_index = min(max(line_no, 1), len(lines)) - 1
        if target_index < 0 or target_index >= len(lines):
            return ""

        target_line = lines[target_index]
        newline = ""
        if target_line.endswith("\r\n"):
            newline = "\r\n"
            line_body = target_line[:-2]
        elif target_line.endswith("\n"):
            newline = "\n"
            line_body = target_line[:-1]
        else:
            line_body = target_line

        stripped = line_body.rstrip()

        if self._looks_like_simple_missing_colon(stripped.strip(), str(error_message or "").lower()):
            comment_index = None
            try:
                for token in tokenize.generate_tokens(io.StringIO(line_body + "\n").readline):
                    if token.type == tokenize.COMMENT:
                        comment_index = token.start[1]
                        break
            except (tokenize.TokenError, IndentationError):
                comment_index = None

            if comment_index is not None:
                prefix = line_body[:comment_index].rstrip()
                suffix = line_body[comment_index:]
                candidate_line = f"{prefix}:{suffix}"
            else:
                candidate_line = f"{line_body.rstrip()}:"

            repaired_lines = list(lines)
            repaired_lines[target_index] = candidate_line + newline
            repaired_source = "".join(repaired_lines)
            try:
                ast.parse(repaired_source)
                return repaired_source
            except SyntaxError:
                pass

        if self._looks_like_plain_text_noise_line(stripped.strip(), str(error_message or "").lower()):
            cleaned = stripped.strip()
            candidate_line = f"# {cleaned}"
            repaired_lines = list(lines)
            repaired_lines[target_index] = candidate_line + newline
            repaired_source = "".join(repaired_lines)
            try:
                ast.parse(repaired_source)
                return repaired_source
            except SyntaxError:
                pass

        for_range_pattern = re.match(r"^(?P<indent>\s*)for\s+(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s+n\s+range\(\)\s*:?\s*$", stripped)
        if for_range_pattern:
            candidate_line = (
                f"{for_range_pattern.group('indent')}for {for_range_pattern.group('target')} in range(n):"
            )
            repaired_lines = list(lines)
            repaired_lines[target_index] = candidate_line + newline
            repaired_source = "".join(repaired_lines)
            try:
                ast.parse(repaired_source)
                return repaired_source
            except SyntaxError:
                pass

        missing_in_pattern = re.match(r"^(?P<indent>\s*)for\s+(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s+range\((?P<arg>[^)]*)\)\s*:?\s*$", stripped)
        if missing_in_pattern:
            arg_text = missing_in_pattern.group("arg").strip()
            if arg_text:
                candidate_line = (
                    f"{missing_in_pattern.group('indent')}for {missing_in_pattern.group('target')} in range({arg_text}):"
                )
                repaired_lines = list(lines)
                repaired_lines[target_index] = candidate_line + newline
                repaired_source = "".join(repaired_lines)
                try:
                    ast.parse(repaired_source)
                    return repaired_source
                except SyntaxError:
                    pass

        return ""

    def _find_unmatched_openers(self, source: str) -> List[str]:
        opener_to_closer = {"(": ")", "[": "]", "{": "}"}
        closer_to_opener = {
            ")": "(",
            "]": "[",
            "}": "{",
        }
        stack: List[str] = []

        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type in {
                    tokenize.STRING,
                    tokenize.COMMENT,
                    tokenize.NL,
                    tokenize.NEWLINE,
                    tokenize.INDENT,
                    tokenize.DEDENT,
                    tokenize.ENDMARKER,
                }:
                    continue
                for character in token.string:
                    if character in opener_to_closer:
                        stack.append(character)
                    elif character in closer_to_opener:
                        expected_opener = closer_to_opener[character]
                        if stack and stack[-1] == expected_opener:
                            stack.pop()
        except (tokenize.TokenError, IndentationError, SyntaxError):
            # Candidate code from LLM may be structurally invalid; do not let
            # tokenizer/parser errors crash the debugging service itself.
            pass

        return stack

    def _is_valid_python(self, code_text: str) -> bool:
        try:
            ast.parse(code_text)
            return True
        except SyntaxError:
            return False

    def _apply_fix(self, script_path: str, fixed_code: str) -> bool:
        if not fixed_code or len(fixed_code) < 2:
            return False

        try:
            with open(script_path, "w", encoding="utf-8") as file_handle:
                file_handle.write(fixed_code)
            return True
        except Exception as exc:
            logger.warning("Failed to write fix: %s", exc)
            return False

    def _save_fixed_script(self, original_path: str, fixed_code: str) -> str:
        try:
            base = os.path.splitext(original_path)[0]
            extension = os.path.splitext(original_path)[1] or ".py"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fixed_path = f"{base}_fixed_{timestamp}{extension}"

            with open(fixed_path, "w", encoding="utf-8") as file_handle:
                file_handle.write(fixed_code)

            return fixed_path
        except Exception as exc:
            logger.warning("Failed to save fixed script: %s", exc)
            return original_path

    def _success_result(
        self,
        script_path: str,
        iteration: int,
        stdout: str,
        stderr: str,
        final_exit_code: int,
        llm_fallback_used: bool,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "success",
            "stdout": stdout,
            "stderr": stderr,
            "iterations": iteration,
            "script_path": script_path,
            "failure_reason": "",
            "final_exit_code": final_exit_code,
            "llm_fallback_used": bool(llm_fallback_used),
        }
        if extra:
            result.update(extra)
        return result

    def _failure_result(
        self,
        script_path: str,
        iteration: int,
        stderr: str,
        error_message: str,
        failure_reason: str,
        final_exit_code: int,
        llm_fallback_used: bool,
    ) -> Dict[str, Any]:
        return {
            "status": "failure",
            "error": error_message,
            "stdout": "",
            "stderr": stderr,
            "iterations": iteration,
            "script_path": script_path,
            "failure_reason": failure_reason,
            "final_exit_code": final_exit_code,
            "llm_fallback_used": bool(llm_fallback_used),
        }


class CodeDebugger:
    """Public interface consumed by orchestrator.py."""

    def __init__(self, executor: Any = None, max_iterations: Optional[int] = None, timeout: Optional[int] = None):
        self.ollama_url = OLLAMA_URL
        self.ollama_model = OLLAMA_MODEL
        self.executor = executor
        self.max_iterations = max_iterations or MAX_DEBUG_ITERATIONS
        self.timeout = timeout or DEBUG_TIMEOUT

    def debug(self, schema_b: dict) -> dict:
        normalized = self._normalize_schema_b(schema_b)
        if "error" in normalized:
            return self._error_result(
                script_path=str(normalized.get("script_path", "")),
                error_message=str(normalized["error"]),
                failure_reason="invalid-schema-b",
                final_exit_code=1,
            )

        if self._stress_enabled(schema_b):
            return self._run_stress_suite(normalized, schema_b)

        script_path = str(normalized["script_path"])
        working_dir = str(normalized["working_dir"])
        python_exe = str(normalized["python_executable"])
        pending_installs = list(normalized.get("pending_installs", []))
        task_id = str(normalized.get("task_id", "unknown"))

        logger.info("[CodeDebugger] task=%s script=%s", task_id, script_path)

        debugger = _SubprocessDebugger(
            python_exe=python_exe,
            working_dir=working_dir,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            max_iterations=self.max_iterations,
            timeout=self.timeout,
            executor=self.executor,
            llm_fallback_max_attempts=LLM_FALLBACK_MAX_ATTEMPTS,
        )

        result = debugger.run(script_path, pending_installs)
        return self._normalize_result(result, script_path)

    def _stress_enabled(self, schema_b: Any) -> bool:
        if not isinstance(schema_b, dict):
            return False
        if "stress_test" in schema_b:
            return bool(schema_b.get("stress_test"))
        if STRESS_ENABLED_DEFAULT:
            logger.info("[CodeDebugger] DEBUG_STRESS_ENABLED is set but ignored for regular runs; use schema_b['stress_test']=true to execute stress suite")
        return False

    def _resolve_stress_log_path(self, schema_b: Any) -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        if isinstance(schema_b, dict):
            log_dir_value = str(schema_b.get("stress_log_dir") or STRESS_LOG_DIR_DEFAULT)
            log_file_value = str(schema_b.get("stress_log_file") or STRESS_LOG_FILE_DEFAULT)
        else:
            log_dir_value = STRESS_LOG_DIR_DEFAULT
            log_file_value = STRESS_LOG_FILE_DEFAULT

        log_dir = Path(log_dir_value)
        if not log_dir.is_absolute():
            log_dir = repo_root / log_dir

        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / log_file_value

    def _append_stress_log(self, log_path: Path, payload: Dict[str, Any]) -> None:
        payload_with_ts = dict(payload)
        payload_with_ts.setdefault("timestamp_utc", datetime.utcnow().isoformat() + "Z")
        with log_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(json.dumps(payload_with_ts, ensure_ascii=True) + "\n")

    def _stress_repeat_count(self, schema_b: Any) -> int:
        profile_to_repeat = {
            "light": 10,
            "medium": 40,
            "heavy": 120,
        }

        repeat = STRESS_REPEAT_DEFAULT
        profile = STRESS_PROFILE_DEFAULT
        explicit_repeat = False
        if isinstance(schema_b, dict):
            if "stress_profile" in schema_b:
                profile = str(schema_b.get("stress_profile") or profile).strip().lower()
            if "stress_repeat" in schema_b:
                try:
                    stress_repeat_value = schema_b.get("stress_repeat")
                    if stress_repeat_value is not None:
                        repeat = int(stress_repeat_value)
                        explicit_repeat = True
                except Exception:
                    repeat = STRESS_REPEAT_DEFAULT

        if not explicit_repeat:
            repeat_from_profile = profile_to_repeat.get(profile)
            if repeat_from_profile is not None:
                repeat = repeat_from_profile

        return max(1, min(200, repeat))

    def _stress_scenarios(self, schema_b: Any) -> List[str]:
        source = STRESS_SCENARIOS_DEFAULT
        if isinstance(schema_b, dict) and schema_b.get("stress_scenarios"):
            source = str(schema_b.get("stress_scenarios"))

        scenarios = [item.strip().lower() for item in source.split(",") if item.strip()]
        if not scenarios:
            scenarios = ["deterministic_module_install_fail", "probabilistic_guardrails_pass"]
        return scenarios

    def _run_stress_case(self, base: Dict[str, Any], scenario: str, case_max_iterations: int) -> Dict[str, Any]:
        global _guardrails_engine
        original_engine = _guardrails_engine

        with tempfile.TemporaryDirectory(prefix="debug_stress_", dir=base["working_dir"]) as temp_dir:
            script_path = os.path.join(temp_dir, "stress_case.py")

            debugger = _SubprocessDebugger(
                python_exe=base["python_executable"],
                working_dir=temp_dir,
                ollama_url=self.ollama_url,
                ollama_model=self.ollama_model,
                max_iterations=case_max_iterations,
                timeout=self.timeout,
                executor=self.executor,
                llm_fallback_max_attempts=1,
                suppress_no_fix_warning=True,
            )

            expected = ""
            try:
                if scenario == "deterministic_module_install_fail":
                    with open(script_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("import definitely_missing_pkg_for_stress_abc123\n")
                    debugger._pip_install = lambda package: False
                    expected = "failure_reason=module-install-failed"

                elif scenario == "syntax_repeat":
                    with open(script_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("def broken(:\n    pass\n")
                    debugger._ask_llm_for_fix_plan = lambda script_path, stderr, error_type, attempt, feedback: None
                    expected = "same error repeated or deterministic syntax failure"

                elif scenario == "probabilistic_guardrails_reject":
                    class _RejectEngine:
                        def validate(self, payload):
                            return {
                                "status": "REJECT",
                                "command_key": None,
                                "token_array": [],
                                "reason": "not allowed",
                                "failing_rule_id": "token_order_step_4",
                            }

                    _guardrails_engine = _RejectEngine()
                    with open(script_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("raise RuntimeError('boom')\n")
                    debugger._ask_llm_for_fix_plan = lambda script_path, stderr, error_type, attempt, feedback: {
                        "proposed_command": "curl http://example.invalid",
                        "corrected_code": "print('x')\n",
                        "reasoning": "reject scenario",
                    }
                    expected = "failure_reason startswith guardrails-reject"

                elif scenario == "probabilistic_guardrails_block":
                    class _BlockEngine:
                        def validate(self, payload):
                            return {
                                "status": "BLOCK",
                                "command_key": None,
                                "token_array": [],
                                "reason": "variable expansion",
                                "failing_rule_id": "token_order_step_2",
                            }

                    _guardrails_engine = _BlockEngine()
                    with open(script_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("raise RuntimeError('boom')\n")
                    debugger._ask_llm_for_fix_plan = lambda script_path, stderr, error_type, attempt, feedback: {
                        "proposed_command": "python $1 script.py",
                        "corrected_code": "print('x')\n",
                        "reasoning": "block scenario",
                    }
                    expected = "failure_reason startswith guardrails-block"

                elif scenario == "probabilistic_guardrails_pass":
                    class _PassEngine:
                        def validate(self, payload):
                            return {
                                "status": "PASS",
                                "command_key": "python_version",
                                "token_array": [base["python_executable"], "-V"],
                                "reason": None,
                                "failing_rule_id": None,
                            }

                    _guardrails_engine = _PassEngine()
                    with open(script_path, "w", encoding="utf-8") as file_handle:
                        file_handle.write("print(undefined_name)\n")
                    debugger._ask_llm_for_fix_plan = lambda script_path, stderr, error_type, attempt, feedback: {
                        "proposed_command": "python -V",
                        "corrected_code": "print('stress fixed')\n",
                        "reasoning": "pass scenario",
                    }
                    expected = "status=success and llm_fallback_used=true"

                else:
                    return {
                        "scenario": scenario,
                        "passed": False,
                        "expected": "known scenario",
                        "result": {
                            "status": "failure",
                            "error": f"Unknown stress scenario: {scenario}",
                            "failure_reason": "unknown-stress-scenario",
                            "final_exit_code": 1,
                            "llm_fallback_used": False,
                        },
                    }

                result = debugger.run(script_path, [])
                passed = False
                failure_reason = str(result.get("failure_reason", ""))
                if scenario == "deterministic_module_install_fail":
                    passed = result.get("status") == "failure" and failure_reason == "module-install-failed"
                elif scenario == "syntax_repeat":
                    passed = (
                        str(result.get("error", "")).startswith("Same error repeated 3 times")
                        or failure_reason.startswith("same-error-repeated")
                        or failure_reason == "deterministic-syntax-error"
                    )
                elif scenario == "probabilistic_guardrails_reject":
                    passed = result.get("status") == "failure" and failure_reason.startswith("guardrails-reject:")
                elif scenario == "probabilistic_guardrails_block":
                    passed = result.get("status") == "failure" and failure_reason.startswith("guardrails-block:")
                elif scenario == "probabilistic_guardrails_pass":
                    passed = (
                        result.get("status") == "success"
                        and bool(result.get("llm_fallback_used"))
                        and int(result.get("final_exit_code", 1)) == 0
                    )

                return {
                    "scenario": scenario,
                    "passed": passed,
                    "expected": expected,
                    "result": {
                        "status": result.get("status"),
                        "failure_reason": result.get("failure_reason"),
                        "final_exit_code": result.get("final_exit_code"),
                        "llm_fallback_used": result.get("llm_fallback_used"),
                        "iterations": result.get("iterations"),
                        "error": str(result.get("error", ""))[:300],
                    },
                }
            finally:
                _guardrails_engine = original_engine

    def _run_stress_suite(self, normalized: Dict[str, Any], schema_b: Any) -> Dict[str, Any]:
        run_id = os.environ.get("DEBUG_STRESS_RUN_ID") or f"stress_{uuid.uuid4().hex[:12]}"
        repeat_count = self._stress_repeat_count(schema_b)
        scenarios = self._stress_scenarios(schema_b)
        log_path = self._resolve_stress_log_path(schema_b)

        self._append_stress_log(
            log_path,
            {
                "event": "stress_run_start",
                "run_id": run_id,
                "task_id": normalized.get("task_id", "unknown"),
                "repeat_count": repeat_count,
                "scenarios": scenarios,
                "python_executable": normalized.get("python_executable"),
                "working_dir": normalized.get("working_dir"),
            },
        )

        case_results: List[Dict[str, Any]] = []
        case_index = 0
        suite_start = time.perf_counter()
        for repeat_index in range(1, repeat_count + 1):
            for scenario in scenarios:
                case_index += 1
                case_start = time.perf_counter()
                case_max_iterations = 2 if scenario == "probabilistic_guardrails_pass" else 1
                if scenario == "syntax_repeat":
                    case_max_iterations = min(max(3, self.max_iterations), 5)

                case_output = self._run_stress_case(normalized, scenario, case_max_iterations)
                duration_ms = int((time.perf_counter() - case_start) * 1000)

                case_record = {
                    "event": "stress_case_result",
                    "run_id": run_id,
                    "case_index": case_index,
                    "repeat_index": repeat_index,
                    "scenario": scenario,
                    "duration_ms": duration_ms,
                    "passed": bool(case_output.get("passed", False)),
                    "expected": case_output.get("expected", ""),
                    "observed": case_output.get("result", {}),
                }
                case_results.append(case_record)
                self._append_stress_log(log_path, case_record)

        total_duration_ms = int((time.perf_counter() - suite_start) * 1000)
        passed_count = sum(1 for item in case_results if item.get("passed"))
        failed_count = len(case_results) - passed_count

        summary = {
            "event": "stress_run_summary",
            "run_id": run_id,
            "total_cases": len(case_results),
            "passed_cases": passed_count,
            "failed_cases": failed_count,
            "duration_ms": total_duration_ms,
            "avg_case_ms": int(total_duration_ms / max(1, len(case_results))),
            "scenarios": scenarios,
            "repeat_count": repeat_count,
        }
        self._append_stress_log(log_path, summary)

        status = "success" if failed_count == 0 else "failure"
        return {
            "status": status,
            "stdout": json.dumps(summary, ensure_ascii=True),
            "stderr": "",
            "iterations": len(case_results),
            "script_path": str(normalized["script_path"]),
            "failure_reason": "" if status == "success" else "stress-cases-failed",
            "final_exit_code": 0 if status == "success" else 1,
            "llm_fallback_used": False,
            "error": "" if status == "success" else f"{failed_count} stress case(s) failed",
            "stress_report": summary,
        }

    def _normalize_schema_b(self, schema_b: Any) -> Dict[str, Any]:
        if not isinstance(schema_b, dict):
            return {"error": "Schema B must be a dictionary"}

        script_path = schema_b.get("script_path")
        if not script_path:
            return {"error": "Schema B missing required field: script_path"}

        script_path_str = os.path.abspath(str(script_path))
        working_dir = schema_b.get("working_dir") or os.path.dirname(script_path_str) or "."
        python_exe = schema_b.get("python_executable") or "python3"
        pending_installs = schema_b.get("pending_installs") or []

        if not isinstance(pending_installs, list):
            pending_installs = [str(pending_installs)]

        normalized = {
            "script_path": script_path_str,
            "working_dir": str(Path(working_dir).resolve()),
            "python_executable": str(python_exe),
            "env_vars": schema_b.get("env_vars") or {},
            "pending_installs": [str(item) for item in pending_installs],
            "task_id": schema_b.get("task_id", "unknown"),
        }

        return normalized

    def _normalize_result(self, result: Dict[str, Any], script_path: str) -> Dict[str, Any]:
        normalized = dict(result or {})
        normalized.setdefault("status", "failure")
        normalized.setdefault("stdout", "")
        normalized.setdefault("stderr", "")
        normalized.setdefault("iterations", 0)
        normalized.setdefault("script_path", script_path)
        normalized.setdefault("failure_reason", "" if normalized.get("status") == "success" else "unknown")
        normalized.setdefault("final_exit_code", 0 if normalized.get("status") == "success" else 1)
        normalized.setdefault("llm_fallback_used", False)

        if normalized.get("status") != "success":
            normalized.setdefault("error", "Debugging failed")

        return normalized

    def _error_result(
        self,
        script_path: str,
        error_message: str,
        failure_reason: str,
        final_exit_code: int,
    ) -> Dict[str, Any]:
        return {
            "status": "failure",
            "error": error_message,
            "stdout": "",
            "stderr": "",
            "iterations": 0,
            "script_path": script_path,
            "failure_reason": failure_reason,
            "final_exit_code": final_exit_code,
            "llm_fallback_used": False,
        }