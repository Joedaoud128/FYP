"""
debugging.py — Adapter Module
==============================
Bridges Raymond's Phase 4/5 SelfCorrectionService into the CodeDebugger
interface that Maria's Orchestrator expects.

The Orchestrator calls:
    debugger = CodeDebugger()
    result = debugger.debug(schema_b)

This adapter translates Schema B fields into the arguments that
SelfCorrectionService.run_target_file() accepts, then translates
the result back into the dict format the Orchestrator consumes.

Author: Integration layer (connects Raymond → Maria)
"""

import os
import sys
import ast
import json
import re
import shlex
import uuid
import importlib
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("debugging")

# ---------------------------------------------------------------------------
# Configuration — matches the SSH tunnel + Ollama setup
# ---------------------------------------------------------------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
MAX_DEBUG_ITERATIONS = int(os.environ.get("MAX_DEBUG_ITERATIONS", "10"))
DEBUG_TIMEOUT = int(os.environ.get("DEBUG_TIMEOUT", "30"))
LLM_FALLBACK_MAX_ATTEMPTS = int(os.environ.get("LLM_FALLBACK_MAX_ATTEMPTS", "2"))


# ---------------------------------------------------------------------------
# In-Shoot Prompt for the LLM fix-generation step (from Elise's document)
# Constrains LLM reasoning to the sandbox's allowed action space before
# it generates a fix proposal. Reduces wasted iterations from rejected
# commands and aligns model reasoning with guardrails policy.
# ---------------------------------------------------------------------------
FIX_GENERATION_PROMPT = """\
You are the fix-generation component of a reactive debugging agent.
You operate inside a containerized sandbox. Your sole task is to propose
the next corrective action (a complete corrected Python file) that will
resolve the current error in the target script.

A guardrails layer validates every command you propose before execution.
To avoid rejected commands and wasted iterations, restrict your proposals
to the approved command set and follow all validation rules below.

== APPROVED COMMANDS =========================================================
Python Execution:
  python -V
  python <script.py>
  python -m py_compile <file.py>

Filesystem Inspection:
  pwd | ls | ls -la | cat <file> | head -n N <file> | tail -n N <file>
  wc -l <file> | diff <file_a> <file_b> | file <path>

Search:
  grep -n "<pattern>" <file>
  grep -R -n "<pattern>" <path>
  find <path> -maxdepth N -type f

Limited File Operations:
  mkdir -p <dir> | cp <src> <dst> | mv <src> <dst> | rm <file>

Dependency Resolution:
  python -m pip show <pkg>
  python -m pip list
  python -m pip install <pkg>

Static Analysis:
  python -m py_compile <file.py>
  python -m ruff check <path>

== VALIDATION RULES ==========================================================
1. Commands must strictly match the whitelist above.
2. Shell operators are forbidden in arguments: ; | && > >>
3. All paths must resolve within the workspace directory.
4. Directory traversal ("../") is not allowed.
5. Symlink escapes are forbidden.
6. find must include -maxdepth with a value <= 4.
7. rm may only target a single file with no flags.
8. Commands must not be chained or combined.

== FIX PROPOSAL RULES ========================================================
1. Classify the error type before proposing a fix.
2. For deterministic errors (ModuleNotFoundError, SyntaxError,
   IndentationError, FileNotFoundError), use the corresponding
   deterministic fix command.
3. For non-deterministic errors, propose a targeted code edit.
4. If the fix cannot be expressed with approved commands,
   report the limitation. Do not invent or escalate commands.
5. Never attempt network access beyond pip install.
6. Return ONLY the complete corrected Python code. No markdown fences.
   No explanatory text outside valid Python.
"""


# ---------------------------------------------------------------------------
# Guardrails integration for the LLM probabilistic path
# Per Elise's Integration Guide: LLM-proposed commands MUST go through
# validate(). Deterministic commands bypass guardrails by design.
# ---------------------------------------------------------------------------
_guardrails_engine = None

def _load_debug_guardrails():
    """Load GuardrailsEngine for validating LLM-proposed commands in the probabilistic path."""
    global _guardrails_engine
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        guardrails_dir = os.path.abspath(os.path.join(here, "..", "guardrails"))
        if os.path.isdir(guardrails_dir) and guardrails_dir not in sys.path:
            sys.path.insert(0, guardrails_dir)

        guardrails_cls = None
        for module_name in ("guardrails_engine", "guardrails.guardrails_engine"):
            try:
                module = importlib.import_module(module_name)
                guardrails_cls = getattr(module, "GuardrailsEngine", None)
                if guardrails_cls is not None:
                    break
            except ImportError:
                continue

        if guardrails_cls is None:
            logger.warning("[Debugging] guardrails_engine.py not available — LLM commands will not be validated")
            return

        # Search multiple possible locations for the config
        candidates = [
            os.path.join(here, "guardrails_config.yaml"),
            os.path.join(here, "..", "guardrails", "guardrails_config.yaml"),
            os.path.join(here, "guardrails", "guardrails_config.yaml"),
        ]
        for cfg_path in candidates:
            if os.path.exists(cfg_path):
                _guardrails_engine = guardrails_cls(cfg_path)
                logger.info("[Debugging] Guardrails engine loaded for LLM probabilistic path")
                return
        logger.warning("[Debugging] guardrails_config.yaml not found — LLM commands will not be validated")
    except Exception as e:
        logger.warning("[Debugging] Failed to load guardrails: %s", e)

_load_debug_guardrails()


# ---------------------------------------------------------------------------
# Attempt to import Raymond's SelfCorrectionService
# ---------------------------------------------------------------------------
_SELF_CORRECTION_AVAILABLE = False
_SelfCorrectionService = None

def _try_import_raymond():
    """Try to import Raymond's module from multiple possible locations."""
    global _SELF_CORRECTION_AVAILABLE, _SelfCorrectionService

    # Possible paths where Raymond's code might live
    here = os.path.dirname(__file__)
    workspace_root = os.path.abspath(os.path.join(here, "..", "..", ".."))
    search_paths = [
        os.path.join(here, "src"),
        os.path.join(here, "..", "debugging", "src"),
        os.path.join(here, "..", "src"),
        os.path.join(workspace_root, "src"),
    ]

    for path in search_paths:
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path) and abs_path not in sys.path:
            sys.path.insert(0, abs_path)

    try:
        from phase4.app.service import SelfCorrectionService  # type: ignore[import]
        _SelfCorrectionService = SelfCorrectionService
        _SELF_CORRECTION_AVAILABLE = True
        logger.info("Raymond's SelfCorrectionService loaded successfully")
    except ImportError as e:
        logger.warning(
            "SelfCorrectionService not available: %s. "
            "Falling back to subprocess-based debugging.", e
        )
        _SELF_CORRECTION_AVAILABLE = False

_try_import_raymond()


# ---------------------------------------------------------------------------
# Fallback: Subprocess-based debug loop
# ---------------------------------------------------------------------------
class _SubprocessDebugger:
    """
    Fallback debugger that uses subprocess to run scripts and
    applies basic deterministic fixes when SelfCorrectionService
    is not importable.

    Handles:
      - ModuleNotFoundError → pip install
      - SyntaxError         → report (cannot auto-fix without LLM)
      - Other errors        → attempt LLM fix via Ollama API

    This is a simplified version of Raymond's logic for demo purposes.
    """

    def __init__(self, python_exe="python3", working_dir=".",
                 ollama_url=OLLAMA_URL, ollama_model=OLLAMA_MODEL,
                 max_iterations=MAX_DEBUG_ITERATIONS,
                 timeout=DEBUG_TIMEOUT, executor=None, env_vars: Optional[dict] = None):
        self.python_exe = python_exe
        self.working_dir = working_dir
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.executor = executor  # Optional Docker executor
        self.env = os.environ.copy()
        if env_vars:
            for key, value in env_vars.items():
                if isinstance(key, str):
                    self.env[key] = str(value)
        self._last_llm_error = ""
        self._llm_fallback_max_attempts = max(1, LLM_FALLBACK_MAX_ATTEMPTS)

    def run(self, script_path: str, pending_installs: Optional[list] = None) -> dict:
        """
        Execute the script, attempt fixes, return result dict.
        """
        # Pre-install any pending packages from Schema B
        if pending_installs:
            for pkg in pending_installs:
                self._pip_install(pkg)

        last_stderr = ""
        last_return_code = 1
        last_failure_reason = ""
        last_error_signature = ""
        same_error_count = 0
        llm_fallback_used = False

        for iteration in range(1, self.max_iterations + 1):
            logger.info("[Debug iter %d/%d] Running %s",
                        iteration, self.max_iterations, script_path)

            result = self._execute(script_path)
            last_return_code = result["return_code"]

            if result["return_code"] == 0 and not result["stderr"].strip():
                logger.info("[Debug iter %d] SUCCESS", iteration)
                return {
                    "status": "success",
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "iterations": iteration,
                    "script_path": script_path,
                    "failure_reason": None,
                    "final_exit_code": 0,
                    "llm_fallback_used": llm_fallback_used,
                }

            stderr = result["stderr"]
            error_type = self._classify_error(stderr)
            error_signature = self._build_error_signature(stderr, error_type)
            logger.info("[Debug iter %d] Error type: %s", iteration, error_type)

            # Same-error detection (max 3 consecutive)
            if error_signature == last_error_signature:
                same_error_count += 1
                if same_error_count >= 3:
                    logger.warning("Same error 3x consecutive — giving up")
                    reason = f"Same error repeated 3 times: {error_type}"
                    return {
                        "status": "failure",
                        "error": reason,
                        "stderr": stderr,
                        "iterations": iteration,
                        "script_path": script_path,
                        "failure_category": error_type,
                        "failure_reason": reason,
                        "final_exit_code": last_return_code,
                        "llm_fallback_used": llm_fallback_used,
                    }
            else:
                same_error_count = 1
                last_error_signature = error_signature

            last_stderr = stderr

            # --- Deterministic fixes (no guardrails needed) ---
            fixed = False

            if error_type == "ModuleNotFoundError":
                module_name = self._extract_module_name(stderr)
                if module_name:
                    logger.info("[Deterministic] pip install %s", module_name)
                    
                    # Try to use Docker executor if available (for sandboxed execution)
                    if self.executor and hasattr(self.executor, 'execute_with_packages'):
                        logger.info("[Docker] Using executor.execute_with_packages for %s", module_name)
                        try:
                            with open(script_path, "r", encoding="utf-8") as f:
                                code = f.read()
                            exec_result = self.executor.execute_with_packages(code, [module_name])
                            if exec_result.return_code == 0:
                                logger.info("[Debug iter %d] SUCCESS with Docker execution", iteration)
                                # Save fixed version with timestamp for user reference
                                fixed_script_path = self._save_fixed_script(script_path, code)
                                return {
                                    "status": "success",
                                    "stdout": exec_result.stdout,
                                    "stderr": exec_result.stderr,
                                    "iterations": iteration,
                                    "script_path": script_path,
                                    "fixed_script_path": fixed_script_path,
                                    "fix_method": f"Docker package install: {module_name}",
                                    "failure_reason": None,
                                    "final_exit_code": 0,
                                    "llm_fallback_used": llm_fallback_used,
                                }
                            else:
                                logger.warning("[Docker] execute_with_packages failed: %s", exec_result.stderr[:200])
                                fixed = False
                        except Exception as e:
                            logger.warning("[Docker] Fallback to pip install: %s", e)
                            fixed = False
                    else:
                        # No Docker executor available, try host pip install
                        success = self._pip_install(module_name)
                        if success:
                            fixed = True
                        else:
                            logger.warning(
                                "pip install %s failed (running in isolated/Docker environment?). "
                                "Cannot auto-fix. Consider using execute_with_packages().", 
                                module_name
                            )
                            # If pip install failed and no Docker executor, give up early
                            return {
                                "status": "failure",
                                "error": (
                                    f"Module '{module_name}' not available and could not be installed. "
                                    f"This may be a Docker/environment isolation issue. "
                                    f"Use orchestrator.execute_with_packages() to install dependencies."
                                ),
                                "stderr": stderr,
                                "iterations": iteration,
                                "script_path": script_path,
                                "failure_category": error_type,
                                "failure_reason": (
                                    f"Module '{module_name}' not available and could not be installed. "
                                    f"This may be a Docker/environment isolation issue. "
                                    f"Use orchestrator.execute_with_packages() to install dependencies."
                                ),
                                "final_exit_code": last_return_code,
                                "llm_fallback_used": llm_fallback_used,
                            }

            elif error_type == "FileNotFoundError":
                logger.info("[Deterministic] FileNotFoundError — cannot auto-fix")

            # --- LLM fallback for other errors (probabilistic path) ---
            # Per Elise's Integration Guide: LLM-proposed commands MUST go
            # through guardrails validate(). The LLM fix here returns corrected
            # Python code (not shell commands), so it is a code-edit action.
            # The FIX_GENERATION_PROMPT constrains reasoning to approved actions.
            # If guardrails are available, we log the LLM fallback event for
            # audit compliance (Module 12 - Logging).
            if not fixed and error_type not in ("ModuleNotFoundError",):
                logger.info("[LLM Fallback] Asking Ollama for fix (probabilistic path)...")
                if _guardrails_engine:
                    logger.info("[Guardrails] LLM probabilistic path active — "
                                "in-shoot prompt constrains to approved action space")
                else:
                    logger.warning("[Guardrails] Engine not loaded — LLM fix "
                                   "will not be validated against policy")
                llm_fallback_used = True
                fixed, fallback_reason = self._run_llm_fallback(script_path, stderr)
                if not fixed and fallback_reason:
                    last_failure_reason = fallback_reason
                    logger.warning("[LLM Fallback] No valid fix applied: %s", fallback_reason)

            if not fixed:
                logger.warning("[Debug iter %d] No fix applied", iteration)

        if not last_failure_reason:
            last_failure_reason = f"Max iterations ({self.max_iterations}) reached"

        return {
            "status": "failure",
            "error": f"Max iterations ({self.max_iterations}) reached",
            "stderr": last_stderr,
            "iterations": self.max_iterations,
            "script_path": script_path,
            "failure_category": self._classify_error(last_stderr),
            "failure_reason": last_failure_reason,
            "final_exit_code": last_return_code,
            "llm_fallback_used": llm_fallback_used,
        }

    def _run_llm_fallback(self, script_path: str, stderr: str) -> tuple[bool, str]:
        """Run bounded probabilistic fallback attempts with contextual retries."""
        current_error = stderr
        last_reason = ""

        for llm_attempt in range(1, self._llm_fallback_max_attempts + 1):
            llm_fix = self._ask_llm_for_fix(script_path, current_error)
            if not llm_fix:
                last_reason = self._last_llm_error or "LLM did not return fix content."
                current_error = (
                    f"{stderr}\n"
                    f"Previous fallback response was invalid: {last_reason}. "
                    "Return corrected complete Python source code only."
                )
                continue

            fixed, reason = self._apply_fix(script_path, llm_fix)
            if fixed:
                return True, ""

            last_reason = reason
            current_error = (
                f"{stderr}\n"
                f"Previous fallback fix failed: {reason}. "
                "Propose an alternative corrected complete Python file."
            )

        return False, last_reason or "LLM fallback attempts exhausted."

    def _execute(self, script_path: str) -> dict:
        """Run the script and capture output."""
        try:
            result = subprocess.run(
                [self.python_exe, script_path],
                capture_output=True, text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                env=self.env,
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
                "stderr": (
                    f"TimeoutError: Execution exceeded {self.timeout}s "
                    f"(script={script_path}, cwd={self.working_dir})."
                ),
            }
        except Exception as e:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"ExecutionError: {e}",
            }

    def _pip_install(self, package: str) -> bool:
        """
        Attempt to install a package using pip.
        Returns True if successful, False otherwise.
        
        Note: When running in Docker execution context, pip install
        may fail silently because the package is installed on the host
        but the script runs in an isolated container. This is expected.
        """
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "install", package],
                capture_output=True, text=True, timeout=60,
                env=self.env,
            )
            success = result.returncode == 0
            if not success:
                logger.warning(
                    "pip install %s returned %d (may be Docker isolation): %s",
                    package, result.returncode,
                    result.stderr[:200] if result.stderr else ""
                )
            return success
        except Exception as e:
            logger.warning("pip install %s exception: %s", package, e)
            return False

    def _classify_error(self, stderr: str) -> str:
        """Simple error classifier."""
        if re.search(r"\b(ModuleNotFoundError|ImportError)\b", stderr):
            return "ModuleNotFoundError"
        if re.search(r"\b(SyntaxError|IndentationError|TabError)\b", stderr):
            return "SyntaxError"
        if re.search(r"\bFileNotFoundError\b", stderr):
            return "FileNotFoundError"
        if re.search(r"\bNameError\b", stderr):
            return "NameError"
        if re.search(r"\bTypeError\b", stderr):
            return "TypeError"
        if re.search(r"\bTimeoutError\b", stderr):
            return "TimeoutError"
        if re.search(r"\b(AttributeError|KeyError|IndexError|ValueError|ZeroDivisionError)\b", stderr):
            return "RuntimeError"
        return "OtherError"

    @staticmethod
    def _build_error_signature(stderr: str, error_type: str) -> str:
        """Create a stable signature from the most actionable traceback line."""
        lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
        if not lines:
            return error_type
        traceback_lines = [line for line in lines if ":" in line and "Error" in line]
        key_line = traceback_lines[-1] if traceback_lines else lines[-1]
        key_line = re.sub(r"\s+", " ", key_line)
        return f"{error_type}|{key_line}"

    def _extract_module_name(self, stderr: str) -> str:
        """Extract module name from ModuleNotFoundError traceback."""
        # Pattern: No module named 'xyz'
        match = re.search(r"No module named '([^']+)'", stderr)
        if match:
            return match.group(1).split(".")[0]
        # Pattern: cannot import name 'X' from 'Y'
        match = re.search(r"cannot import name .+ from '([^']+)'", stderr)
        if match:
            return match.group(1).split(".")[0]
        # Pattern: from .foo import bar (relative import failure)
        match = re.search(r"from\s+\.([A-Za-z_][A-Za-z0-9_\.]*)\s+import", stderr)
        if match:
            return match.group(1).split(".")[0]
        return ""

    def _ask_llm_for_fix(self, script_path: str, stderr: str) -> str:
        """
        Ask Ollama to propose a fix for the error.
        
        Uses the FIX_GENERATION_PROMPT (In-Shoot Prompt from Elise's document)
        as the system message to constrain LLM reasoning to the sandbox's
        allowed action space. This reduces wasted iterations from rejected
        commands and aligns model reasoning with the guardrails policy.
        """
        import urllib.request
        import urllib.error
        self._last_llm_error = ""

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception as e:
            self._last_llm_error = f"Failed to read source file: {e}"
            return ""

        prompt = (
            f"=== CODE ===\n{code[:3000]}\n\n"
            f"=== ERROR ===\n{stderr[:1500]}\n\n"
            "Classify this error, then return the corrected complete Python file:"
        )

        payload = json.dumps({
            "model": self.ollama_model,
            "messages": [
                {"role": "system", "content": FIX_GENERATION_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2048},
        }).encode()

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            content = data.get("message", {}).get("content", "")
            if not isinstance(content, str) or not content.strip():
                self._last_llm_error = "Model response did not contain fix content."
                return ""
            return content.strip()
        except urllib.error.HTTPError as e:
            self._last_llm_error = f"HTTP {e.code}: {e.reason}"
            logger.warning("LLM fallback failed: %s", self._last_llm_error)
            return ""
        except urllib.error.URLError as e:
            self._last_llm_error = f"Network error: {getattr(e, 'reason', e)}"
            logger.warning("LLM fallback failed: %s", self._last_llm_error)
            return ""
        except json.JSONDecodeError as e:
            self._last_llm_error = f"Invalid JSON from LLM endpoint: {e}"
            logger.warning("LLM fallback failed: %s", self._last_llm_error)
            return ""
        except Exception as e:
            self._last_llm_error = str(e)
            logger.warning("LLM fallback failed: %s", self._last_llm_error)
            return ""

    @staticmethod
    def _normalize_llm_code(fixed_code: str) -> str:
        """Normalize LLM output to raw Python content."""
        if not fixed_code:
            return ""
        content = fixed_code.strip().replace("\r\n", "\n")
        lines = content.splitlines()

        # Remove leading markdown fence with optional language tag.
        if lines and (lines[0].strip().startswith("```") or lines[0].strip().startswith("~~~")):
            lines = lines[1:]
        # Remove trailing markdown fence.
        if lines and (lines[-1].strip() == "```" or lines[-1].strip() == "~~~"):
            lines = lines[:-1]

        # Trim obvious non-code lead-ins.
        while lines and lines[0].strip().lower().startswith(("here is", "corrected code", "fixed code")):
            lines = lines[1:]

        return "\n".join(lines).strip()

    @staticmethod
    def _is_valid_python(code: str) -> tuple[bool, str]:
        """Validate candidate fix looks like valid Python source."""
        try:
            ast.parse(code)
            compile(code, "<llm_fix>", "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} (line {e.lineno})"
        except Exception as e:
            return False, str(e)

    def _validate_probabilistic_guardrails(self, script_path: str) -> tuple[bool, str]:
        """Enforce guardrails validation for the probabilistic path when available."""
        if _guardrails_engine is None:
            return True, "guardrails unavailable; probabilistic path running in degraded mode"

        abs_script = os.path.abspath(script_path)
        abs_workdir = os.path.abspath(self.working_dir)
        try:
            if os.path.commonpath([abs_script, abs_workdir]) != abs_workdir:
                return False, f"Script path escapes working_dir: {abs_script}"
        except ValueError:
            return False, f"Script path and working_dir are on different drives: {abs_script}"

        raw_command = f"python -m py_compile {shlex.quote(abs_script)}"
        try:
            response = _guardrails_engine.validate(
                {
                    "caller_service": "debugging",
                    "raw_command": raw_command,
                    "working_dir": abs_workdir,
                }
            )
        except Exception as e:
            return False, f"Guardrails validation error: {e}"

        status = response.get("status", "REJECT")
        if status != "PASS":
            return False, (
                "Guardrails blocked probabilistic action. "
                f"status={status}; reason={response.get('reason')}; "
                f"failing_rule_id={response.get('failing_rule_id')}"
            )

        return True, ""

    def _apply_fix(self, script_path: str, fixed_code: str) -> tuple[bool, str]:
        """Validate and write LLM-proposed code back to the script file safely."""
        cleaned = self._normalize_llm_code(fixed_code)
        if not cleaned or len(cleaned) < 10:
            logger.warning("Rejected LLM fix: empty or too small after normalization")
            return False, "Rejected LLM fix: empty or too small after normalization"

        valid, reason = self._is_valid_python(cleaned)
        if not valid:
            logger.warning("Rejected LLM fix: %s", reason)
            return False, f"Rejected LLM fix: {reason}"

        allowed, guardrails_reason = self._validate_probabilistic_guardrails(script_path)
        if not allowed:
            logger.warning("Rejected LLM fix due to guardrails: %s", guardrails_reason)
            return False, guardrails_reason

        backup_path = f"{script_path}.bak"
        temp_path = f"{script_path}.tmp"
        try:
            with open(script_path, "r", encoding="utf-8") as src:
                original = src.read()
            with open(backup_path, "w", encoding="utf-8") as backup:
                backup.write(original)
            with open(temp_path, "w", encoding="utf-8") as tmp:
                tmp.write(cleaned)
            os.replace(temp_path, script_path)
            if os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except OSError:
                    pass
            logger.info("Applied LLM fix to %s", script_path)
            return True, ""
        except Exception as e:
            logger.warning("Failed to apply validated fix: %s", e)
            try:
                if os.path.exists(backup_path):
                    os.replace(backup_path, script_path)
            except Exception as rollback_error:
                logger.warning("Rollback failed: %s", rollback_error)
            return False, f"Failed to apply validated fix: {e}"
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _save_fixed_script(self, original_path: str, fixed_code: str) -> str:
        """
        Save a copy of the fixed script with a timestamp suffix.
        Returns the path to the saved fixed script.
        """
        try:
            # Get base name without extension
            base = os.path.splitext(original_path)[0]
            extension = os.path.splitext(original_path)[1] or ".py"
            
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fixed_path = f"{base}_fixed_{timestamp}_{uuid.uuid4().hex[:8]}{extension}"
            
            # Write fixed code
            with open(fixed_path, "w", encoding="utf-8") as f:
                f.write(fixed_code)
            
            logger.info("Saved fixed script to %s", fixed_path)
            return fixed_path
        except Exception as e:
            logger.warning("Failed to save fixed script: %s", e)
            return original_path  # Fallback to original if save fails


# ---------------------------------------------------------------------------
# CodeDebugger — the interface the Orchestrator expects
# ---------------------------------------------------------------------------
class CodeDebugger:
    """
    Public interface consumed by orchestrator.py.

    Usage (from orchestrator):
        debugger = CodeDebugger(executor=orchestrator.executor)
        result = debugger.debug(schema_b)

    Schema B fields used:
        script_path         — path to the Python script to debug
        working_dir         — working directory for execution
        python_executable   — which Python binary to use
        pending_installs    — packages to pre-install before first run
        task_id             — task identifier (passed through)
    """

    def __init__(self, executor=None, max_iterations=None, timeout=None):
        self.ollama_url = OLLAMA_URL
        self.ollama_model = OLLAMA_MODEL
        self.executor = executor  # Optional Docker executor from orchestrator
        self.max_iterations = max_iterations or MAX_DEBUG_ITERATIONS
        self.timeout = timeout or DEBUG_TIMEOUT

    def debug(self, schema_b: dict) -> dict:
        """
        Run the debug loop on the script specified in Schema B.

        Returns:
            {
                "status": "success" | "failure",
                "stdout": str,
                "stderr": str,
                "iterations": int,
                "script_path": str,
                "error": str (on failure only),
            }
        """
        if not isinstance(schema_b, dict):
            return {
                "status": "failure",
                "error": "Invalid schema_b: expected dict",
                "stdout": "",
                "stderr": "",
                "iterations": 0,
                "script_path": "",
                "failure_category": "InputValidationError",
                "failure_reason": "Invalid schema_b: expected dict",
                "final_exit_code": 1,
                "llm_fallback_used": False,
            }

        script_path_raw = str(schema_b.get("script_path", "")).strip()
        if not script_path_raw:
            return {
                "status": "failure",
                "error": "Missing required field: script_path",
                "stdout": "",
                "stderr": "",
                "iterations": 0,
                "script_path": "",
                "failure_category": "InputValidationError",
                "failure_reason": "Missing required field: script_path",
                "final_exit_code": 1,
                "llm_fallback_used": False,
            }

        working_dir_raw = str(schema_b.get("working_dir", "")).strip()
        if not working_dir_raw:
            default_workdir = os.path.dirname(script_path_raw)
            working_dir_raw = default_workdir if default_workdir else os.getcwd()

        working_dir = os.path.abspath(working_dir_raw)
        if not os.path.isdir(working_dir):
            return {
                "status": "failure",
                "error": f"working_dir does not exist: {working_dir}",
                "stdout": "",
                "stderr": "",
                "iterations": 0,
                "script_path": script_path_raw,
                "failure_category": "InputValidationError",
                "failure_reason": f"working_dir does not exist: {working_dir}",
                "final_exit_code": 1,
                "llm_fallback_used": False,
            }

        script_path = script_path_raw
        if not os.path.isabs(script_path):
            script_path = os.path.join(working_dir, script_path)
        script_path = os.path.abspath(script_path)

        if not os.path.isfile(script_path):
            return {
                "status": "failure",
                "error": f"script_path does not exist or is not a file: {script_path}",
                "stdout": "",
                "stderr": "",
                "iterations": 0,
                "script_path": script_path,
                "failure_category": "FileNotFoundError",
                "failure_reason": f"script_path does not exist or is not a file: {script_path}",
                "final_exit_code": 1,
                "llm_fallback_used": False,
            }

        python_exe = str(schema_b.get("python_executable", sys.executable or "python3")).strip() or (sys.executable or "python3")
        pending_installs_raw = schema_b.get("pending_installs", [])
        pending_installs = pending_installs_raw if isinstance(pending_installs_raw, list) else []
        env_vars_raw = schema_b.get("env_vars", {})
        env_vars = env_vars_raw if isinstance(env_vars_raw, dict) else {}
        task_id = schema_b.get("task_id", "unknown")

        logger.info(
            "[CodeDebugger] Starting debug for task=%s script=%s",
            task_id, script_path
        )

        if _SELF_CORRECTION_AVAILABLE and _SelfCorrectionService is not None:
            return self._debug_via_raymond(
                script_path, python_exe, working_dir, pending_installs, env_vars
            )
        else:
            return self._debug_via_fallback(
                script_path, python_exe, working_dir, pending_installs, env_vars
            )

    def _debug_via_raymond(self, script_path, python_exe, working_dir, pending_installs, env_vars):
        """Use Raymond's SelfCorrectionService directly."""
        try:
            service = _SelfCorrectionService(  # type: ignore[misc]
                python_executable=python_exe,
                workspace_root=working_dir,
                use_llm_fallback=True,
                ollama_base_url=self.ollama_url,
                ollama_model=self.ollama_model,
                max_iterations=self.max_iterations,
                run_timeout_seconds=self.timeout,
            )

            result = service.run_target_file(script_path)
            outcome = service.to_outcome(result)

            if outcome.success:
                return {
                    "status": "success",
                    "stdout": "",
                    "stderr": "",
                    "iterations": outcome.attempts,
                    "script_path": script_path,
                    "failure_reason": outcome.failure_reason,
                    "final_exit_code": outcome.final_exit_code,
                    "llm_fallback_used": bool(getattr(result, "llm_fallback_used", False)),
                }
            else:
                return {
                    "status": "failure",
                    "error": outcome.failure_reason or "Debug loop exhausted",
                    "stdout": "",
                    "stderr": outcome.final_stderr or "",
                    "iterations": outcome.attempts,
                    "script_path": script_path,
                    "failure_reason": outcome.failure_reason or "Debug loop exhausted",
                    "final_exit_code": outcome.final_exit_code,
                    "llm_fallback_used": bool(getattr(result, "llm_fallback_used", False)),
                }

        except Exception as e:
            logger.error("SelfCorrectionService raised: %s", e)
            # Fall back to subprocess debugger
            return self._debug_via_fallback(
                script_path,
                python_exe,
                working_dir,
                pending_installs,
                env_vars,
            )

    def _debug_via_fallback(self, script_path, python_exe,
                            working_dir, pending_installs, env_vars=None):
        """Use the built-in subprocess-based debugger with optional Docker executor."""
        debugger = _SubprocessDebugger(
            python_exe=python_exe,
            working_dir=working_dir,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            max_iterations=self.max_iterations,
            timeout=self.timeout,
            executor=self.executor,  # Pass Docker executor if available
            env_vars=env_vars,
        )
        result = debugger.run(script_path, pending_installs)
        result.setdefault("failure_reason", result.get("error"))
        result.setdefault("final_exit_code", 0 if result.get("status") == "success" else 1)
        result.setdefault("llm_fallback_used", False)
        return result
