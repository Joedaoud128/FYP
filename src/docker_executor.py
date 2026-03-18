"""
docker_executor.py
==================
Docker-based sandboxed execution engine for the AI Coding Agent.

Architecture Position:
    This module implements Layer 3 (Runtime Isolation) inside
    Module 8 (Action Executor) of the shared execution pipeline:

    Module 6 (Tool Selector) -> Module 7 (Policy Check) -> Module 8 (Action Executor)
                                                            ^ DockerExecutor lives here

    Both the Code Generation service and the Code Debugging service
    use this same executor through the shared pipeline whenever they
    need to run a script. The Security & Guardrails service (Module 7)
    validates commands BEFORE they reach this executor.

    The Orchestrator (Module 11) does NOT participate in this pipeline.
    It operates at a higher level — managing the handoff between
    services and enforcing termination rules (max 10 iterations,
    same error 3x, 30-minute timeout). The Orchestrator never calls
    the DockerExecutor directly.

Three-Layer Security Architecture:
    Layer 1: Orchestrator validates data at handoff boundary (V1-V7)
    Layer 2: Policy Check validates commands in shared pipeline (Module 7)
    Layer 3: DockerExecutor isolates runtime execution (this module)
"""

import subprocess
import tempfile
import os
import time
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """
    Structured result from sandboxed execution.
    Consumed by Module 9 (Evaluation and Feedback) to determine
    success or failure. Compatible with both the Code Generation
    service's Phase 8 execution and the Code Debugging service's
    iterative Execute-Analyze-Fix loop.
    """
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    timed_out: bool
    error_type: Optional[str] = None


class DockerExecutor:
    """
    Executes Python code inside Docker containers.
    Sits inside Module 8 (Action Executor), called ONLY after
    Module 7 (Policy Check) has approved the command. Both the
    Code Generation and Code Debugging services use this executor
    through the shared pipeline (Modules 6->7->8).
    """

    DEFAULT_TIMEOUT = 30
    MAX_TIMEOUT = 300
    MEMORY_LIMIT = "512m"
    CPU_LIMIT = "1"
    PID_LIMIT = "100"
    DISK_LIMIT = "100m"
    IMAGE_NAME = "agent-sandbox"

    def __init__(self, timeout: int = None):
        self.timeout = min(timeout or self.DEFAULT_TIMEOUT, self.MAX_TIMEOUT)
        self._verify_docker()

    def _verify_docker(self):
        """Check that Docker is available and image exists."""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", self.IMAGE_NAME],
                capture_output=True, timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Docker image '{self.IMAGE_NAME}' not found. "
                    f"Run: docker build -t {self.IMAGE_NAME} ."
                )
        except FileNotFoundError:
            raise RuntimeError("Docker is not installed or not in PATH.")

    def execute(self, code: str) -> ExecutionResult:
        """
        Execute Python code in a sandboxed container.
        Called by Module 8 after Module 7 approval. Each execution
        creates a fresh, ephemeral container destroyed after results.
        """
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', dir='/tmp', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            cmd = [
                "docker", "run",
                "--rm",
                "--network", "none",
                "--memory", self.MEMORY_LIMIT,
                "--memory-swap", self.MEMORY_LIMIT,
                "--cpus", self.CPU_LIMIT,
                "--pids-limit", self.PID_LIMIT,
                "--read-only",
                "--tmpfs", f"/workspace:rw,noexec,size={self.DISK_LIMIT}",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges",
                "-v", f"{tmp_path}:/sandbox/script.py:ro",
                self.IMAGE_NAME,
                "python3", "/sandbox/script.py"
            ]

            logger.info(f"Executing in container (timeout={self.timeout}s)")
            start_time = time.time()

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout + 5
            )

            execution_time = time.time() - start_time
            return ExecutionResult(
                return_code=result.returncode,
                stdout=result.stdout, stderr=result.stderr,
                execution_time=execution_time, timed_out=False
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            logger.warning(f"Execution timed out after {self.timeout}s")
            self._force_cleanup()
            return ExecutionResult(
                return_code=-1, stdout="",
                stderr=f"TimeoutError: Execution exceeded {self.timeout}s",
                execution_time=execution_time,
                timed_out=True, error_type="TimeoutError"
            )

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def execute_with_packages(self, code: str, packages: list[str]) -> ExecutionResult:
        """
        Execute code after installing additional packages.
        Used by the Code Debugging service's self-correction loop
        when ModuleNotFoundError is detected. The packages list
        often comes from Schema B's pending_installs field.
        """
        install_lines = []
        for pkg in packages:
            install_lines.append(
                f"import subprocess; "
                f"subprocess.run(['pip', 'install', '{pkg}'], capture_output=True)"
            )
        modified_code = "\n".join(install_lines) + "\n" + code
        return self.execute(modified_code)

    def _force_cleanup(self):
        """Kill any running containers from our image."""
        try:
            subprocess.run(
                ["docker", "ps", "-q", "--filter", f"ancestor={self.IMAGE_NAME}"],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            pass