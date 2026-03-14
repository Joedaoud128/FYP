"""
orchestrator.py
===============
Module 11: Agent Orchestrator (Control Loop)

This is the meta-controller of the AI Coding Agent. It oversees
the entire pipeline, manages the handoff between Code Generation
(Joe) and Code Debugging (Raymond), and enforces termination rules.

Two entry points:
    - run_generate(prompt) : Generate Mode (full pipeline)
    - run_debug(script_path) : Debug Mode (skip generation)

Termination rules (from architecture spec):
    - Maximum 10 iterations
    - Same error 3 consecutive times → halt
    - 30-minute session timeout

Architecture reference: Module 11 in Figure 1 (AI Coding Agent
Workflow), represented as the dashed purple border.

Author: Maria (Orchestrator)
"""

import os
import time
import json
import logging
import subprocess
from datetime import datetime
from typing import Optional

from orchestrator_handoff import (
    HandoffValidator,
    EnvironmentPreparer,
    HandoffValidationError,
    process_handoff,
)

import sys
import shutil
from docker_executor import DockerExecutor


def _detect_system_python() -> str:
    if sys.platform == "win32":
        if shutil.which("python"):
            return "python"
    if shutil.which("python3"):
        return "python3"
    if shutil.which("python"):
        return "python"
    return sys.executable


# The default Python command for this system
SYSTEM_PYTHON = _detect_system_python()


# ──────────────────────────────────────────────
# Orchestrator Configuration
# ──────────────────────────────────────────────

class OrchestratorConfig:
    """
    Central configuration for the Orchestrator.
    Values can be overridden via environment variables
    (set in docker-compose.yml for container deployment).
    """
    MAX_ITERATIONS: int = int(
        os.environ.get("MAX_ITERATIONS", "10")
    )
    MAX_SAME_ERROR: int = int(
        os.environ.get("MAX_SAME_ERROR", "3")
    )
    SESSION_TIMEOUT: int = int(
        os.environ.get("SESSION_TIMEOUT", "1800")  # 30 min
    )
    EXECUTION_TIMEOUT: int = int(
        os.environ.get("EXECUTION_TIMEOUT", "60")  # per script
    )
    WORKSPACE_DIR: str = os.environ.get(
        "WORKSPACE_DIR", "/workspace"
    )


# ──────────────────────────────────────────────
# Execution Result (returned by each iteration)
# ──────────────────────────────────────────────

class ExecutionResult:
    """
    Structured result from a single script execution.
    Maps to what the Execution Engine (Phase 8) returns:
    return code, stdout, stderr, and execution time.
    """

    def __init__(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        execution_time: float,
        error_type: Optional[str] = None,
    ):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
        self.error_type = error_type
        self.success = (exit_code == 0 and not stderr.strip())

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time": self.execution_time,
            "error_type": self.error_type,
            "success": self.success,
        }


# ──────────────────────────────────────────────
# Main Orchestrator Class (Module 11)
# ──────────────────────────────────────────────

class Orchestrator:
    """
    Module 11: Agent Orchestrator / Control Loop.

    The meta-controller that:
    1. Manages the handoff from Code Generation to Code Debugging
    2. Runs the Execute-Analyze-Fix loop
    3. Enforces termination rules (max iterations, repeated
       errors, session timeout)
    4. Logs all orchestrator-level events (Module 12 source)

    Usage:
        orch = Orchestrator()

        # Generate Mode (full pipeline)
        result = orch.run_generate("Write a script to ...")

        # Debug Mode (existing script)
        result = orch.run_debug("/workspace/input/broken.py")
    """

    def __init__(self, config: OrchestratorConfig = None):
        self.config = config or OrchestratorConfig()
        self.logger = logging.getLogger("orchestrator")

        # ── State tracking ──
        self.iteration = 0
        self.error_history = []
        self.session_start = None

        # ── Handoff components (from Step 3) ──
        self.validator = HandoffValidator()
        self.preparer = EnvironmentPreparer()

    # ══════════════════════════════════════════
    # ENTRY POINT 1: Generate Mode
    # ══════════════════════════════════════════

    def run_generate(self, prompt: str) -> dict:
        """
        Full pipeline: User prompt → Code Generation (Joe) →
        Handoff Validation → Environment Preparation →
        Debug Loop (Raymond) → Result.

        This is the Generate Mode entry point.

        Args:
            prompt: Natural language task description from user.

        Returns:
            Final result dict with status, output, and metadata.
        """
        self._start_session()
        self.logger.info(
            "=== GENERATE MODE START === Prompt: %s", prompt
        )

        # ── Phase 1: Call Joe's Code Generation module ──
        # (Joe's module is imported and called here.
        #  Replace with actual import when Joe's code is ready.)
        try:
            generation_output = self._call_code_generation(prompt)
        except Exception as e:
            self.logger.error(
                "Code generation failed: %s", str(e)
            )
            return self._build_result(
                status="failure",
                reason="generation_error",
                error=str(e),
            )

        # ── Phase 2: Validate handoff (your code from Step 3) ──
        try:
            validated = self.validator.validate(generation_output)
        except HandoffValidationError as e:
            self.logger.error(
                "Handoff validation failed: %s", str(e)
            )
            return self._build_result(
                status="failure",
                reason="handoff_validation_error",
                error=str(e),
            )

        # ── Phase 3: Prepare execution context ──
        exec_context = self.preparer.prepare(validated)

        # ── Phase 4: Enter the debug loop ──
        return self._run_debug_loop(exec_context)

    # ══════════════════════════════════════════
    # ENTRY POINT 2: Debug Mode
    # ══════════════════════════════════════════

    def run_debug(self, script_path: str) -> dict:
        """
        Debug Mode: Skip generation, go directly to the
        Execute-Analyze-Fix loop with an existing script.

        This is invoked as:
            python agent.py --mode debug --fix broken_script.py

        Args:
            script_path: Path to the broken Python script.

        Returns:
            Final result dict with status, output, and metadata.
        """
        self._start_session()
        self.logger.info(
            "=== DEBUG MODE START === Script: %s", script_path
        )

        # Build a minimal execution context (no generation data)
        exec_context = {
            "script_path": os.path.abspath(script_path),
            "working_dir": os.path.dirname(
                os.path.abspath(script_path)
            ),
            "python_executable": SYSTEM_PYTHON,
            "env_vars": {},
            "task_id": f"debug_{int(time.time())}",
        }

        # Validate the script exists and is inside workspace
        if not os.path.isfile(exec_context["script_path"]):
            return self._build_result(
                status="failure",
                reason="script_not_found",
                error=f"File not found: {script_path}",
            )

        return self._run_debug_loop(exec_context)

    # ══════════════════════════════════════════
    # THE DEBUG LOOP (Execute-Analyze-Fix)
    # ══════════════════════════════════════════

    def _run_debug_loop(self, exec_context: dict) -> dict:
        """
        The core Execute-Analyze-Fix loop.

        This implements the iterative debugging cycle from
        the Code Debugging Workflow (Figure 3):
            Step 2: Execute script
            Step 3: Check exit code
            Step 4: Iteration control
            Step 5: Parse stderr
            Step 6: Error classifier
            Steps 7-8: Apply fix and loop back

        The Orchestrator manages the loop. Raymond's module
        handles the actual execution, classification, and fixing.

        Args:
            exec_context: Schema B payload (execution_context).

        Returns:
            Final result dict.
        """
        self.logger.info(
            "Entering debug loop for task: %s",
            exec_context["task_id"]
        )

        while self.iteration < self.config.MAX_ITERATIONS:
            self.iteration += 1

            # ── Check session timeout ──
            if self._is_session_timed_out():
                self.logger.error(
                    "Session timeout reached (%d seconds)",
                    self.config.SESSION_TIMEOUT
                )
                return self._build_result(
                    status="failure",
                    reason="session_timeout",
                    error=(
                        f"Session exceeded "
                        f"{self.config.SESSION_TIMEOUT}s limit"
                    ),
                    exec_context=exec_context,
                )

            self.logger.info(
                "── Iteration %d / %d ──",
                self.iteration, self.config.MAX_ITERATIONS
            )

            # ── Step 2: Execute the script ──
            result = self._execute_script(exec_context)

            # ── Step 3: Check exit code ──
            if result.success:
                self.logger.info(
                    "Script executed successfully on "
                    "iteration %d", self.iteration
                )
                return self._build_result(
                    status="success",
                    output=result.stdout,
                    exec_context=exec_context,
                )

            # ── Step 4: Check for repeated errors ──
            self.error_history.append(result.error_type)

            if self._is_same_error_repeated():
                self.logger.error(
                    "Same error '%s' occurred %d consecutive "
                    "times. Halting.",
                    result.error_type,
                    self.config.MAX_SAME_ERROR,
                )
                return self._build_result(
                    status="failure",
                    reason="repeated_error",
                    error=result.error_type,
                    stderr=result.stderr,
                    exec_context=exec_context,
                )

            # ── Steps 5-8: Classify error and apply fix ──
            # (This is Raymond's domain. The orchestrator calls
            #  his module and receives an updated exec_context.)
            exec_context = self._call_debug_fix(
                exec_context, result
            )

        # ── Max iterations exhausted ──
        self.logger.error(
            "Max iterations (%d) reached. Halting.",
            self.config.MAX_ITERATIONS
        )
        return self._build_result(
            status="failure",
            reason="max_iterations",
            error=(
                f"Could not fix script after "
                f"{self.config.MAX_ITERATIONS} attempts"
            ),
            exec_context=exec_context,
        )

    # ══════════════════════════════════════════
    # EXECUTION (calls Module 8: Action Executor)
    # ══════════════════════════════════════════

def _execute_script(
        self, exec_context: dict
    ) -> ExecutionResult:
        """
        Execute the script inside a Docker container using
        the DockerExecutor sandbox.

        This corresponds to Phase 8 (Execution Engine) in the
        code generation workflow and Step 2 in the debug workflow.

        The script is read from disk, its contents are passed
        to DockerExecutor.execute(), which runs it inside an
        isolated container with all guardrails enforced:
        --network none, --memory 512m, --read-only, etc.
        """
        script = exec_context["script_path"]

        self.logger.debug(
            "Executing in Docker sandbox: %s (timeout=%ds)",
            script, self.config.EXECUTION_TIMEOUT
        )

        # Read the script contents from disk
        try:
            with open(script, "r") as f:
                code = f.read()
        except FileNotFoundError:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"FileNotFoundError: Script not found: {script}",
                execution_time=0.0,
                error_type="FileNotFoundError",
            )

        # Execute inside Docker container
        executor = DockerExecutor(
            timeout=self.config.EXECUTION_TIMEOUT
        )
        docker_result = executor.execute(code)

        # Map DockerExecutor result to orchestrator's ExecutionResult
        result = ExecutionResult(
            exit_code=docker_result.return_code,
            stdout=docker_result.stdout,
            stderr=docker_result.stderr,
            execution_time=docker_result.execution_time,
            error_type=(
                docker_result.error_type
                or self._classify_error_type(docker_result.stderr)
            ),
        )

        self.logger.info(
            "Execution result: exit_code=%d, time=%.2fs, "
            "error_type=%s",
            result.exit_code,
            result.execution_time,
            result.error_type or "none",
        )

        return result
    # ══════════════════════════════════════════
    # ERROR CLASSIFICATION (basic, for orchestrator)
    # ══════════════════════════════════════════

    def _classify_error_type(self, stderr: str) -> Optional[str]:
        """
        Basic error classification from stderr content.
        This maps to Step 6 (Error Classifier) in the debug
        workflow. Raymond's module provides the full hybrid
        (deterministic + probabilistic) classifier.

        The Orchestrator only needs a simplified version to
        track repeated errors for its termination logic.
        """
        if not stderr or not stderr.strip():
            return None

        # Deterministic patterns (from debug workflow)
        error_patterns = {
            "ModuleNotFoundError": "ModuleNotFoundError",
            "ImportError": "ImportError",
            "SyntaxError": "SyntaxError",
            "IndentationError": "IndentationError",
            "FileNotFoundError": "FileNotFoundError",
            "NameError": "NameError",
            "TypeError": "TypeError",
            "ValueError": "ValueError",
            "TimeoutError": "TimeoutError",
            "ConnectionError": "ConnectionError",
        }

        for pattern, error_type in error_patterns.items():
            if pattern in stderr:
                return error_type

        return "UnclassifiedError"

    # ══════════════════════════════════════════
    # DEBUG FIX (calls Raymond's module)
    # ══════════════════════════════════════════

    def _call_debug_fix(
        self,
        exec_context: dict,
        result: ExecutionResult,
    ) -> dict:
        """
        Call Raymond's debugging module to analyze the error
        and apply a fix.

        This is a placeholder that will be replaced with the
        actual import of Raymond's code_debugger module when
        it is ready. The interface contract is:

        Input:  exec_context (Schema B) + ExecutionResult
        Output: updated exec_context (with fix applied)

        Raymond's module handles:
            - Step 5: Parse stderr output
            - Step 6: Error classifier (hybrid)
            - Step 7: Select corrective tool
            - Step 8: Apply fix (write file / pip install)
        """
        self.logger.info(
            "Calling debug module: error_type=%s",
            result.error_type
        )

        # ──────────────────────────────────────────
        # TODO: Replace with actual import when
        #       Raymond's module is ready:
        #
        #   from code_debugger import DebugModule
        #   debugger = DebugModule()
        #   exec_context = debugger.analyze_and_fix(
        #       exec_context, result
        #   )
        # ──────────────────────────────────────────

        # Placeholder: log what would happen
        self.logger.warning(
            "DEBUG MODULE PLACEHOLDER - In production, "
            "Raymond's code_debugger.analyze_and_fix() "
            "would be called here with error_type=%s",
            result.error_type,
        )

        return exec_context

    # ══════════════════════════════════════════
    # CODE GENERATION (calls Joe's module)
    # ══════════════════════════════════════════

    def _call_code_generation(self, prompt: str) -> dict:
        """
        Call Joe's code generation module to produce a script
        from a natural language prompt.

        This is a placeholder that will be replaced with the
        actual import of Joe's code_generator module when it
        is ready. The interface contract is:

        Input:  Natural language prompt (string)
        Output: generation_output (Schema A)

        Joe's module handles:
            - Phase 2: Environment extraction
            - Phase 3: Requirement parsing
            - Phase 4: Multi-step planner (ReAct loop)
            - Phase 5: Library identification & validation
            - Phase 6: Code generation (LLM)
            - Phase 7: Syntax validation (AST parse)
            - Phase 8: Write script to disk
        """
        self.logger.info(
            "Calling code generation module with prompt: %s",
            prompt[:100]
        )

        # ──────────────────────────────────────────
        # TODO: Replace with actual import when
        #       Joe's module is ready:
        #
        #   from code_generator import GenerateModule
        #   generator = GenerateModule()
        #   return generator.generate(prompt)
        # ──────────────────────────────────────────

        raise NotImplementedError(
            "Code generation module is not yet integrated. "
            "Replace this placeholder with Joe's module."
        )

    # ══════════════════════════════════════════
    # TERMINATION CHECKS
    # ══════════════════════════════════════════

    def _is_same_error_repeated(self) -> bool:
        """
        Check if the same error type has occurred N
        consecutive times (default: 3).
        This is a termination condition from Module 11 spec.
        """
        n = self.config.MAX_SAME_ERROR
        if len(self.error_history) < n:
            return False

        last_n = self.error_history[-n:]
        return len(set(last_n)) == 1

    def _is_session_timed_out(self) -> bool:
        """
        Check if the session has exceeded the timeout limit
        (default: 30 minutes / 1800 seconds).
        """
        if self.session_start is None:
            return False

        elapsed = time.time() - self.session_start
        return elapsed > self.config.SESSION_TIMEOUT

    # ══════════════════════════════════════════
    # SESSION MANAGEMENT
    # ══════════════════════════════════════════

    def _start_session(self) -> None:
        """Initialize session state for a new run."""
        self.iteration = 0
        self.error_history = []
        self.session_start = time.time()
        self.logger.info(
            "Session started at %s | Config: "
            "max_iter=%d, max_same_error=%d, timeout=%ds",
            datetime.now().isoformat(),
            self.config.MAX_ITERATIONS,
            self.config.MAX_SAME_ERROR,
            self.config.SESSION_TIMEOUT,
        )

    def _build_result(self, **kwargs) -> dict:
        """
        Build a standardized result dictionary.
        This is what gets returned to the user or logged.

        Includes orchestrator metadata: iteration count,
        session duration, error history, and termination reason.
        """
        elapsed = 0.0
        if self.session_start:
            elapsed = time.time() - self.session_start

        result = {
            "status": kwargs.get("status", "unknown"),
            "reason": kwargs.get("reason"),
            "output": kwargs.get("output"),
            "error": kwargs.get("error"),
            "stderr": kwargs.get("stderr"),
            "orchestrator_metadata": {
                "iterations": self.iteration,
                "session_duration_seconds": round(elapsed, 2),
                "error_history": self.error_history,
                "termination_reason": kwargs.get(
                    "reason", "success"
                ),
                "timestamp": datetime.now().isoformat(),
            },
        }

        # Include task_id if exec_context is provided
        exec_ctx = kwargs.get("exec_context")
        if exec_ctx:
            result["task_id"] = exec_ctx.get("task_id")

        self.logger.info(
            "=== SESSION END === Status: %s | "
            "Iterations: %d | Duration: %.1fs | "
            "Reason: %s",
            result["status"],
            self.iteration,
            elapsed,
            result["reason"] or "success",
        )

        return result


# ──────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────

def main():
    """
    Command-line entry point for the AI Coding Agent.

    Usage:
        # Generate Mode
        python orchestrator.py --mode generate \
            --prompt "Write a script to display Microsoft stock"

        # Debug Mode
        python orchestrator.py --mode debug \
            --fix /workspace/input/broken_script.py
    """
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(name)s] "
            "%(levelname)s: %(message)s"
        ),
    )

    parser = argparse.ArgumentParser(
        description="AI Coding Agent - Orchestrator (Module 11)"
    )
    parser.add_argument(
        "--mode",
        choices=["generate", "debug"],
        required=True,
        help="Operation mode: generate or debug",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Natural language prompt (Generate Mode)",
    )
    parser.add_argument(
        "--fix",
        type=str,
        default=None,
        help="Path to script to debug (Debug Mode)",
    )
    args = parser.parse_args()

    orch = Orchestrator()

    if args.mode == "generate":
        if not args.prompt:
            parser.error(
                "--prompt is required for Generate Mode"
            )
        result = orch.run_generate(args.prompt)

    elif args.mode == "debug":
        if not args.fix:
            parser.error(
                "--fix is required for Debug Mode"
            )
        result = orch.run_debug(args.fix)

    # Print the final result
    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()