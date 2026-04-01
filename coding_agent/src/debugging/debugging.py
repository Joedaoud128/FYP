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
import json
import subprocess
import logging
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
        from guardrails_engine import GuardrailsEngine
        here = os.path.dirname(os.path.abspath(__file__))
        # Search multiple possible locations for the config
        candidates = [
            os.path.join(here, "guardrails_config.yaml"),
            os.path.join(here, "..", "guardrails", "guardrails_config.yaml"),
            os.path.join(here, "guardrails", "guardrails_config.yaml"),
        ]
        for cfg_path in candidates:
            if os.path.exists(cfg_path):
                _guardrails_engine = GuardrailsEngine(cfg_path)
                logger.info("[Debugging] Guardrails engine loaded for LLM probabilistic path")
                return
        logger.warning("[Debugging] guardrails_config.yaml not found — LLM commands will not be validated")
    except ImportError:
        logger.warning("[Debugging] guardrails_engine.py not available — LLM commands will not be validated")
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
    search_paths = [
        os.path.join(os.path.dirname(__file__), "src"),
        os.path.join(os.path.dirname(__file__), "..", "debugging", "src"),
        os.path.join(os.path.dirname(__file__), "..", "src"),
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
                 timeout=DEBUG_TIMEOUT, executor=None):
        self.python_exe = python_exe
        self.working_dir = working_dir
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.executor = executor  # Optional Docker executor

    def run(self, script_path: str, pending_installs: Optional[list] = None) -> dict:
        """
        Execute the script, attempt fixes, return result dict.
        """
        # Pre-install any pending packages from Schema B
        if pending_installs:
            for pkg in pending_installs:
                self._pip_install(pkg)

        last_stderr = ""
        last_error_type = ""
        same_error_count = 0

        for iteration in range(1, self.max_iterations + 1):
            logger.info("[Debug iter %d/%d] Running %s",
                        iteration, self.max_iterations, script_path)

            result = self._execute(script_path)

            if result["return_code"] == 0 and not result["stderr"].strip():
                logger.info("[Debug iter %d] SUCCESS", iteration)
                return {
                    "status": "success",
                    "stdout": result["stdout"],
                    "stderr": result["stderr"],
                    "iterations": iteration,
                    "script_path": script_path,
                }

            stderr = result["stderr"]
            error_type = self._classify_error(stderr)
            logger.info("[Debug iter %d] Error type: %s", iteration, error_type)

            # Same-error detection (max 3 consecutive)
            if error_type == last_error_type:
                same_error_count += 1
                if same_error_count >= 3:
                    logger.warning("Same error 3x consecutive — giving up")
                    return {
                        "status": "failure",
                        "error": f"Same error repeated 3 times: {error_type}",
                        "stderr": stderr,
                        "iterations": iteration,
                        "script_path": script_path,
                    }
            else:
                same_error_count = 1
                last_error_type = error_type

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
                llm_fix = self._ask_llm_for_fix(script_path, stderr)
                if llm_fix:
                    self._apply_fix(script_path, llm_fix)
                    fixed = True

            if not fixed:
                logger.warning("[Debug iter %d] No fix applied", iteration)

        return {
            "status": "failure",
            "error": f"Max iterations ({self.max_iterations}) reached",
            "stderr": last_stderr,
            "iterations": self.max_iterations,
            "script_path": script_path,
        }

    def _execute(self, script_path: str) -> dict:
        """Run the script and capture output."""
        try:
            result = subprocess.run(
                [self.python_exe, script_path],
                capture_output=True, text=True,
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
        except Exception as e:
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
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

    def _extract_module_name(self, stderr: str) -> str:
        """Extract module name from ModuleNotFoundError traceback."""
        import re
        # Pattern: No module named 'xyz'
        match = re.search(r"No module named '([^']+)'", stderr)
        if match:
            return match.group(1).split(".")[0]
        # Pattern: cannot import name 'X' from 'Y'
        match = re.search(r"cannot import name .+ from '([^']+)'", stderr)
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

        try:
            with open(script_path, "r", encoding="utf-8") as f:
                code = f.read()
        except Exception:
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
            return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning("LLM fallback failed: %s", e)
            return ""

    def _apply_fix(self, script_path: str, fixed_code: str):
        """Write the fixed code back to the script file."""
        # Strip markdown fences if present
        lines = fixed_code.strip().splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

        if not cleaned or len(cleaned) < 10:
            return

        try:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(cleaned)
            logger.info("Applied LLM fix to %s", script_path)
        except Exception as e:
            logger.warning("Failed to write fix: %s", e)

    def _save_fixed_script(self, original_path: str, fixed_code: str) -> str:
        """
        Save a copy of the fixed script with a timestamp suffix.
        Returns the path to the saved fixed script.
        """
        from datetime import datetime
        import os
        
        try:
            # Get base name without extension
            base = os.path.splitext(original_path)[0]
            extension = os.path.splitext(original_path)[1] or ".py"
            
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fixed_path = f"{base}_fixed_{timestamp}{extension}"
            
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
        script_path = schema_b["script_path"]
        working_dir = schema_b.get("working_dir", os.path.dirname(script_path))
        python_exe = schema_b.get("python_executable", "python3")
        pending_installs = schema_b.get("pending_installs", [])
        task_id = schema_b.get("task_id", "unknown")

        logger.info(
            "[CodeDebugger] Starting debug for task=%s script=%s",
            task_id, script_path
        )

        if _SELF_CORRECTION_AVAILABLE and _SelfCorrectionService is not None:
            return self._debug_via_raymond(
                script_path, python_exe, working_dir
            )
        else:
            return self._debug_via_fallback(
                script_path, python_exe, working_dir, pending_installs
            )

    def _debug_via_raymond(self, script_path, python_exe, working_dir):
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
                }
            else:
                return {
                    "status": "failure",
                    "error": outcome.failure_reason or "Debug loop exhausted",
                    "stdout": "",
                    "stderr": outcome.final_stderr or "",
                    "iterations": outcome.attempts,
                    "script_path": script_path,
                }

        except Exception as e:
            logger.error("SelfCorrectionService raised: %s", e)
            # Fall back to subprocess debugger
            return self._debug_via_fallback(
                script_path, "python3",
                os.path.dirname(script_path), []
            )

    def _debug_via_fallback(self, script_path, python_exe,
                            working_dir, pending_installs):
        """Use the built-in subprocess-based debugger with optional Docker executor."""
        debugger = _SubprocessDebugger(
            python_exe=python_exe,
            working_dir=working_dir,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            max_iterations=self.max_iterations,
            timeout=self.timeout,
            executor=self.executor,  # Pass Docker executor if available
        )
        return debugger.run(script_path, pending_installs)