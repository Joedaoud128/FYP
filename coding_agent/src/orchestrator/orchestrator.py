"""
orchestrator.py
===============
Orchestrator Module 11 - Full Demo Pipeline

Wires together:
    - Code Generation  (Joe's ProactiveCodeGenerator)
    - DockerExecutor   (Maria's sandboxed execution engine) 
    - Handoff          (Maria's HandoffValidator + EnvironmentPreparer)
    - Code Debugging   (Raymond's debugger via debugging.py adapter)
    - Guardrails       (Elise's GuardrailsEngine — LLM commands only)

Two modes:
    Generate Mode  — user provides a natural language prompt
    Debug Mode     — user provides an existing broken script path

Termination rules (Module 11):
    - Max 10 debug iterations
    - Same error 3 consecutive times → give up
    - 30-minute overall session timeout

Author: Maria (Orchestrator)
"""

import os
import sys
import json
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

# ── Path setup for microservice structure ─────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
for _subdir in ["../generation", "../debugging", "../guardrails", "../execution", ".", "../../docker"]:
    _p = os.path.abspath(os.path.join(_HERE, _subdir))
    if _p not in sys.path:
        sys.path.insert(0, _p)
# Also add current dir so co-located modules work
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Internal modules ──────────────────────────────────────────────────────────
from orchestrator_handoff import (
    process_handoff,
    HandoffValidationError,
    MissingFieldError,
    GenerationFailedError,
    FileValidationError,
    PathSecurityError,
)

# ── Docker executor — optional for demo ──────────────────────────────────────
DOCKER_AVAILABLE = False
try:
    from docker_executor import DockerExecutor, ExecutionResult
    # Quick check if Docker is actually functional
    _check = subprocess.run(
        ["docker", "info"], capture_output=True, timeout=5
    )
    if _check.returncode == 0:
        DOCKER_AVAILABLE = True
except (ImportError, FileNotFoundError, subprocess.TimeoutExpired):
    pass

if not DOCKER_AVAILABLE:
    print("[Orchestrator] WARNING: Docker not available — using subprocess execution")

# ── Code Generation module ───────────────────────────────────────────────────
GENERATION_AVAILABLE = False
try:
    from generation import ProactiveCodeGenerator, QwenCoderClient
    GENERATION_AVAILABLE = True
except ImportError:
    print("[Orchestrator] WARNING: generation.py not found — Generate Mode unavailable")

# ── Code Debugging module (via adapter) ─────────────────────────────────
DEBUGGING_AVAILABLE = False
try:
    from debugging import CodeDebugger
    DEBUGGING_AVAILABLE = True
except ImportError:
    print("[Orchestrator] WARNING: debugging.py not found — debug loop unavailable")

# ── Guardrails Engine ────────────────────────────────────────────────────────
GUARDRAILS_AVAILABLE = False
try:
    from guardrails_engine import GuardrailsEngine
    GUARDRAILS_AVAILABLE = True
except ImportError:
    print("[Orchestrator] WARNING: guardrails_engine.py not found — guardrails disabled")

# ── Logging ───────────────────────────────────────────────────────────────────
try:
    from agent_logger import get_logger as _get_logger
    logger = _get_logger("orchestrator")
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    logger = logging.getLogger("orchestrator")

# ── Memory store — optional, never crashes the pipeline ───────────────────────
try:
    import memory_store as _memory_store   # type: ignore[import]
except ImportError:
    _memory_store = None  # type: ignore[assignment]

# ── Termination constants ─────────────────────────────────────────────────────
MAX_DEBUG_ITERATIONS = 10
MAX_SAME_ERROR_COUNT = 3
MAX_HANDOFF_RETRIES = 2         # outer retry loop: re-generate if debug still fails
SESSION_TIMEOUT_SECONDS = 1800  # 30 minutes


# ── Subprocess fallback executor (when Docker is unavailable) ────────────────
class SubprocessExecutor:
    """
    Lightweight executor that runs Python code via subprocess.
    Used as a fallback when Docker is not available (demo environment).
    Provides the same interface as DockerExecutor.
    """

    def __init__(self, timeout=30):
        self.timeout = timeout

    def execute(self, code: str):
        """Execute code via subprocess, returning an ExecutionResult-like dict."""
        import tempfile
        import time

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=self.timeout,
                encoding='utf-8', errors='replace',
            )
            elapsed = time.time() - start
            return _ExecutionResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=elapsed,
                timed_out=False,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.time() - start
            return _ExecutionResult(
                return_code=-1,
                stdout="",
                stderr=f"TimeoutError: Execution exceeded {self.timeout}s",
                execution_time=elapsed,
                timed_out=True,
                error_type="TimeoutError",
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def execute_with_packages(self, code: str, packages: list):
        """Install packages first, then execute."""
        for pkg in packages:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True, text=True, timeout=120,
                    encoding='utf-8', errors='replace',
                )
            except Exception as e:
                logger.warning("pip install %s failed: %s", pkg, e)
        return self.execute(code)


class _ExecutionResult:
    """Mimics DockerExecutor's ExecutionResult dataclass."""
    def __init__(self, return_code, stdout, stderr, execution_time,
                 timed_out, error_type=None):
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
        self.timed_out = timed_out
        self.error_type = error_type


class Orchestrator:
    """
    Meta-controller for the full AI Coding Agent pipeline.

    Generate Mode flow:
        1. Call CodeGenerator → script file path + metadata
        2. Build Schema A        → from CodeGenerator output
        3. Execute via Docker    → sandboxed run (or subprocess fallback)
        4. Success               → return to user (no debugging)
        5. Failure               → validate Schema A → build Schema B
        6. Call CodeDebugger     → Execute→Analyze→Fix loop
        7. Return final result

    Debug Mode flow:
        1. Build minimal Schema B from user-provided script path
        2. Call CodeDebugger's debug loop
        3. Return final result
    """

    def __init__(self):
        # Choose executor based on Docker availability
        if DOCKER_AVAILABLE:
            try:
                self.executor = DockerExecutor()  # type: ignore[possibly-undefined]
                logger.info("Using DockerExecutor for sandboxed execution")
            except Exception as e:
                logger.warning("DockerExecutor init failed: %s — using subprocess", e)
                self.executor = SubprocessExecutor()
        else:
            self.executor = SubprocessExecutor()

        self.session_start = datetime.now()

        # Initialise guardrails engine if available
        self.guardrails = None
        if GUARDRAILS_AVAILABLE:
            try:
                # Search multiple possible locations for the config
                config_candidates = [
                    Path(__file__).parent / "guardrails_config.yaml",
                    Path(__file__).parent / "../guardrails/guardrails_config.yaml",
                    Path(__file__).parent / "guardrails" / "guardrails_config.yaml",
                ]
                for config_path in config_candidates:
                    if config_path.exists():
                        self.guardrails = GuardrailsEngine(str(config_path))  # type: ignore[possibly-undefined]
                        logger.info("Guardrails engine loaded from %s", config_path)
                        break
                else:
                    logger.warning("guardrails_config.yaml not found in any expected location")
            except Exception as e:
                logger.warning("Failed to load guardrails engine: %s", e)

    # ── PUBLIC ENTRY POINTS ───────────────────────────────────────────────────

    def run_generate(self, prompt: str) -> dict:
        """
        Generate Mode: generate code from a prompt, execute it,
        and debug if needed.
        """
        if not GENERATION_AVAILABLE:
            return {
                "status": "error",
                "error": "Code Generation service not available. "
                         "Ensure generation.py is in the same directory."
            }

        task_id     = f"gen_{uuid.uuid4().hex[:8]}"
        _orch_start = datetime.now()
        logger.info("=== Generate Mode | task_id=%s ===", task_id)
        logger.info("Prompt: %s", prompt[:100])

        # ── Step 1: Call Code Generation service ─────────────────────────────
        logger.info("[Step 1] Calling Code Generation service...")
        try:
            llm = QwenCoderClient()  # type: ignore[possibly-undefined]
            generator = ProactiveCodeGenerator(llm_client=llm)  # type: ignore[possibly-undefined]
            generation_result = generator.generate_from_prompt(prompt)
        except Exception as e:
            logger.error("Code Generation service failed: %s", e)
            return {"status": "error", "error": f"Generation service error: {e}"}

        if generation_result.get("status") != "success":
            logger.error(
                "Generation failed at Stage %s: %s",
                generation_result.get("stage"), generation_result.get("error")
            )
            return {
                "status": "error",
                "error": generation_result.get("error", "Generation failed"),
                "stage": generation_result.get("stage"),
            }

        script_path = generation_result["file_path"]
        requirements = self._extract_requirements(generation_result)

        logger.info("[Step 1] Generation complete. Script: %s", script_path)
        logger.info("[Step 1] Requirements: %s", requirements)

        # ── Step 2: Execute the generated script ─────────────────────────────
        logger.info("[Step 2] Executing generated script...")
        try:
            with open(script_path, "r", encoding="utf-8") as _f:
                generated_code = _f.read()
        except Exception as e:
            return {"status": "error", "error": f"Could not read generated script: {e}"}

        if requirements:
            exec_result = self.executor.execute_with_packages(generated_code, requirements)
        else:
            exec_result = self.executor.execute(generated_code)

        logger.info(
            "[Step 2] exit_code=%d | time=%.2fs | stderr=%s",
            exec_result.return_code,
            exec_result.execution_time,
            exec_result.stderr[:200] if exec_result.stderr else "none"
        )

        # ── Step 3: Decision Point ────────────────────────────────────────────
        if exec_result.return_code == 0:
            # Exit code 0 = success. Stderr may contain library warnings
            # (e.g. DeprecationWarning, ResourceWarning) — not failures.
            if exec_result.stderr.strip():
                logger.info(
                    "[Step 3] Script exited cleanly (code 0) with stderr "
                    "warnings (not treated as failure):\n%s",
                    exec_result.stderr[:300]
                )
            logger.info("[Step 3] SUCCESS — script ran clean, no debugging needed.")
            _result = {
                "status": "success",
                "stdout": exec_result.stdout,
                "stderr": exec_result.stderr,
                "script_path": script_path,
                "execution_time": exec_result.execution_time,
                "task_id": task_id,
                "functions": generation_result.get("functions", []),
                "classes": generation_result.get("classes", []),
                # stats fields threaded from generation.py
                "token_usage":        generation_result.get("token_usage", {}),
                "injection_detected": generation_result.get("injection_detected", False),
                "syntax_repairs":     generation_result.get("syntax_repairs", 0),
                "fallback_used":      generation_result.get("fallback_used", False),
                "handoff_retries":    0,
                "venv_created":       False,
                "docker_used":        DOCKER_AVAILABLE,
                "exit_code":          exec_result.return_code,
            }
            try:
                if _memory_store is not None:
                    _memory_store.record_outcome(
                        task_id=task_id, mode="generate", prompt=prompt,
                        status="success",
                        total_time_s=round(
                            (datetime.now() - _orch_start).total_seconds(), 3
                        ),
                    )
            except Exception:
                pass
            return _result

        logger.info(
            "[Step 3] FAILURE (exit_code=%d) — triggering handoff to debugger.",
            exec_result.return_code
        )

        # ── Step 4: Build Schema A ────────────────────────────────────────────
        schema_a = self._build_schema_a(
            generation_result=generation_result,
            task_id=task_id,
            script_path=script_path,
            requirements=requirements,
            original_prompt=prompt,   # raw user intent forwarded to debugger
        )

        # ── Step 5: Validate Schema A → produce Schema B ─────────────────────
        logger.info("[Step 5] Running handoff validation (V1–V7)...")
        try:
            schema_b = process_handoff(schema_a)
        except MissingFieldError as e:
            return {"status": "error", "error": f"Handoff failed (missing fields): {e}"}
        except GenerationFailedError as e:
            return {"status": "error", "error": f"Handoff failed (generation status): {e}"}
        except FileValidationError as e:
            return {"status": "error", "error": f"Handoff failed (file not found): {e}"}
        except PathSecurityError as e:
            return {"status": "error", "error": f"Handoff failed (path security): {e}"}
        except HandoffValidationError as e:
            return {"status": "error", "error": f"Handoff failed: {e}"}

        logger.info("[Step 5] Handoff validation passed. Schema B ready.")

        # ── Step 6: Call CodeDebugger ──────────────────────────────────────────────
        _result = self._run_debug_loop(schema_b, task_id)

        # ── Step 7: Handoff retry loop ───────────────────────────────────────
        # If debugging fails, re-generate with feedback and retry,
        # up to MAX_HANDOFF_RETRIES times. This resolves a design-
        # implementation gap where V1–V7 validation failures or exhausted
        # debug iterations previously halted the pipeline immediately.
        _handoff_retries = 0
        while (
            _result.get("status") != "success"
            and _handoff_retries < MAX_HANDOFF_RETRIES
        ):
            _handoff_retries += 1
            elapsed = (datetime.now() - self.session_start).total_seconds()
            if elapsed > SESSION_TIMEOUT_SECONDS:
                logger.warning("[Retry] Session timeout — skipping retry %d", _handoff_retries)
                break

            logger.info(
                "[Retry %d/%d] Debugging failed (reason: %s). "
                "Re-generating code with error feedback...",
                _handoff_retries, MAX_HANDOFF_RETRIES,
                _result.get("failure_reason", _result.get("error", "unknown")),
            )

            # Re-generate: the original prompt is enriched with the error
            # from the previous attempt so the LLM can avoid the same mistake.
            try:
                feedback_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: A previous attempt to generate this code failed "
                    f"during debugging with the following error:\n"
                    f"{(_result.get('error') or _result.get('stderr', ''))[:500]}\n"
                    f"Please generate corrected code that avoids this issue."
                )
                generation_result = generator.generate_from_prompt(feedback_prompt)
            except Exception as e:
                logger.error("[Retry %d] Re-generation failed: %s", _handoff_retries, e)
                break

            if generation_result.get("status") != "success":
                logger.error("[Retry %d] Re-generation returned non-success", _handoff_retries)
                break

            script_path = generation_result["file_path"]
            requirements = self._extract_requirements(generation_result)

            # Re-execute
            try:
                with open(script_path, "r", encoding="utf-8") as _f:
                    generated_code = _f.read()
            except Exception as e:
                logger.error("[Retry %d] Could not read re-generated script: %s", _handoff_retries, e)
                break

            if requirements:
                exec_result = self.executor.execute_with_packages(generated_code, requirements)
            else:
                exec_result = self.executor.execute(generated_code)

            if exec_result.return_code == 0:
                logger.info("[Retry %d] Re-generated script runs clean!", _handoff_retries)
                _result = {
                    "status": "success",
                    "stdout": exec_result.stdout,
                    "stderr": exec_result.stderr,
                    "script_path": script_path,
                    "execution_time": exec_result.execution_time,
                    "task_id": task_id,
                    "functions": generation_result.get("functions", []),
                    "classes": generation_result.get("classes", []),
                    "handoff_retries": _handoff_retries,
                }
                break

            # Re-generated code still fails — try debugging again
            schema_a = self._build_schema_a(
                generation_result=generation_result,
                task_id=task_id,
                script_path=script_path,
                requirements=requirements,
                original_prompt=prompt,
            )
            try:
                schema_b = process_handoff(schema_a)
            except HandoffValidationError as e:
                logger.error("[Retry %d] Handoff validation failed: %s", _handoff_retries, e)
                break

            _result = self._run_debug_loop(schema_b, task_id)

        # Enrich with generation-level stats so the entry point can write run stats
        _result.setdefault("token_usage",        generation_result.get("token_usage", {}))
        _result.setdefault("injection_detected", generation_result.get("injection_detected", False))
        _result.setdefault("syntax_repairs",     generation_result.get("syntax_repairs", 0))
        _result.setdefault("fallback_used",      generation_result.get("fallback_used", False))
        _result.setdefault("handoff_retries",    _handoff_retries)
        _result.setdefault("venv_created",       schema_a.get("venv_created", False))
        _result.setdefault("docker_used",        DOCKER_AVAILABLE)
        _result.setdefault("exit_code",
                           0 if _result.get("status") == "success" else 1)
        try:
            if _memory_store is not None:
                _err = _result.get("error") or _result.get("stderr", "")
                # Use failure_reason from debugging.py (structured category like
                # "same-error-repeated:ModuleNotFoundError") over the raw error
                # message, which produces better memory store fingerprints.
                _error_type = _result.get("failure_reason") or _result.get("error")
                _memory_store.record_outcome(
                    task_id=task_id, mode="generate", prompt=prompt,
                    status=_result.get("status", "error"),
                    total_time_s=round(
                        (datetime.now() - _orch_start).total_seconds(), 3
                    ),
                    debug_iterations=_result.get("iterations", 0),
                    error_type=_error_type,
                    failed_stage=str(_result.get("stage", "")) or None,
                )
                if _err and _result.get("status") != "success":
                    _memory_store.record_error(_err, source_module="orchestrator")
        except Exception:
            pass
        return _result

    def run_debug(self, script_path: str) -> dict:
        """
        Debug Mode: debug an existing broken script.
        Bypasses generation and handoff entirely.
        """
        if not os.path.isfile(script_path):
            return {"status": "error", "error": f"Script not found: {script_path}"}

        task_id     = f"dbg_{uuid.uuid4().hex[:8]}"
        _orch_start = datetime.now()
        logger.info("=== Debug Mode | task_id=%s ===", task_id)
        logger.info("Script: %s", script_path)

        schema_b = {
            "script_path": os.path.abspath(script_path),
            "working_dir": str(Path(script_path).parent.resolve()),
            "python_executable": sys.executable,
            "env_vars": {},
            "task_id": task_id,
        }

        _result = self._run_debug_loop(schema_b, task_id)
        _result.setdefault("docker_used", DOCKER_AVAILABLE)
        _result.setdefault("exit_code",
                           0 if _result.get("status") == "success" else 1)
        try:
            if _memory_store is not None:
                _err = _result.get("error") or _result.get("stderr", "")
                _error_type = _result.get("failure_reason") or _result.get("error")
                _memory_store.record_outcome(
                    task_id=task_id, mode="debug", prompt=script_path,
                    status=_result.get("status", "error"),
                    total_time_s=round(
                        (datetime.now() - _orch_start).total_seconds(), 3
                    ),
                    debug_iterations=_result.get("iterations", 0),
                    error_type=_error_type,
                )
                if _err and _result.get("status") != "success":
                    _memory_store.record_error(_err, source_module="debugging")
        except Exception:
            pass
        return _result

    # ── INTERNAL PIPELINE METHODS ─────────────────────────────────────────────

    def _run_debug_loop(self, schema_b: dict, task_id: str) -> dict:
        """
        Pass Schema B to CodeDebugger.
        Enforces termination rules.
        """
        if not DEBUGGING_AVAILABLE:
            logger.warning("Code Debugger not available.")
            return {
                "status": "failure",
                "error": "Code Debugging service not available. "
                         "Ensure debugging.py is in the same directory.",
                "task_id": task_id,
            }

        # Session timeout check
        elapsed = (datetime.now() - self.session_start).total_seconds()
        if elapsed > SESSION_TIMEOUT_SECONDS:
            return {
                "status": "failure",
                "error": f"Session timeout ({SESSION_TIMEOUT_SECONDS // 60} min exceeded).",
                "task_id": task_id,
            }

        logger.info("[Debug Loop] Passing Schema B to Code Debugger...")
        logger.info("[Debug Loop] script=%s", schema_b.get("script_path"))
        logger.info("[Debug Loop] python=%s", schema_b.get("python_executable"))
        logger.info("[Debug Loop] pending_installs=%s", schema_b.get("pending_installs", []))

        try:
            debugger = CodeDebugger(  # type: ignore[possibly-undefined]
                executor=self.executor,
                max_iterations=MAX_DEBUG_ITERATIONS,
            )
            result = debugger.debug(schema_b)
        except Exception as e:
            logger.error("Code Debugger raised an exception: %s", e)
            return {
                "status": "error",
                "error": f"Debugging service error: {e}",
                "task_id": task_id,
            }

        logger.info(
            "[Debug Loop] status=%s | iterations=%s",
            result.get("status"), result.get("iterations", "?")
        )

        result["task_id"] = task_id
        return result

    def _build_schema_a(
        self,
        generation_result: dict,
        task_id: str,
        script_path: str,
        requirements: list,
        original_prompt: str = "",   # raw user intent; forwarded to debugger via Schema B
    ) -> dict:
        """Convert generate_from_prompt() output to Schema A."""
        workspace_dir = str(Path(script_path).parent)
        return {
            "task_id": task_id,
            "generated_script": script_path,
            "requirements": requirements,
            "workspace_dir": workspace_dir,
            "venv_created": generation_result.get("venv_created", False),
            "venv_path": generation_result.get("venv_path"),
            "generation_status": "success",
            "original_prompt": original_prompt,   # top-level so handoff copies it into Schema B
            "metadata": {
                "complexity": str(generation_result.get("complexity", 5)),
                "domain": generation_result.get("task_type", "general"),
                "estimated_libraries": len(requirements),
                "generation_timestamp": datetime.now().isoformat(),
            },
        }

    def _extract_requirements(self, generation_result: dict) -> list:
        """Extract pip requirements from generation result."""
        if "requirements" in generation_result:
            return generation_result.get("requirements", [])
        req_analysis = generation_result.get("requirements_analysis", {})
        if req_analysis and "libraries" in req_analysis:
            return req_analysis.get("libraries", [])
        return []

    def _validate_llm_command(
        self, command: str, working_dir: str, caller: str = "generation"
    ) -> dict:
        """Validate an LLM-proposed command through guardrails."""
        if not self.guardrails:
            return {"status": "PASS", "token_array": command.split()}

        response = self.guardrails.validate({
            "caller_service": caller,
            "raw_command": command,
            "working_dir": working_dir,
        })

        if response["status"] != "PASS":
            logger.warning(
                "Guardrails %s: %s | rule=%s | reason=%s",
                response["status"], command,
                response.get("failing_rule_id"),
                response.get("reason"),
            )

        return response


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="AI Coding Agent — Orchestrator (Module 11)"
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    gen_parser = subparsers.add_parser(
        "generate",
        help="Generate and run code from a natural language prompt"
    )
    gen_parser.add_argument("prompt", help="Natural language task description")

    dbg_parser = subparsers.add_parser(
        "debug",
        help="Debug an existing broken Python script"
    )
    dbg_parser.add_argument("script", help="Path to the broken Python script")

    args = parser.parse_args()
    orch = Orchestrator()

    result: dict = {}
    if args.mode == "generate":
        print(f"\n{'='*60}")
        print(f"AI Coding Agent — Generate Mode")
        print(f"Prompt: {args.prompt}")
        print(f"{'='*60}\n")
        result = orch.run_generate(args.prompt)

    elif args.mode == "debug":
        print(f"\n{'='*60}")
        print(f"AI Coding Agent — Debug Mode")
        print(f"Script: {args.script}")
        print(f"{'='*60}\n")
        result = orch.run_debug(args.script)

    print(f"\n{'='*60}")
    print(f"RESULT: {result.get('status', 'unknown').upper()}")
    print(f"{'='*60}")

    if result.get("status") == "success":
        print(f"\nOutput:\n{result.get('stdout', '(no output)')}")
        if result.get("script_path"):
            print(f"Script: {result.get('script_path')}")
        if result.get("iterations"):
            print(f"Debug iterations: {result.get('iterations')}")
    else:
        print(f"\nError: {result.get('error', 'Unknown error')}")
        if result.get("stderr"):
            print(f"Stderr:\n{result.get('stderr')}")

    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())