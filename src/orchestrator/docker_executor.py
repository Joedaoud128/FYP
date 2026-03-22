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

Package Installation Note:
    Containers run with --network none, so pip install cannot be run
    inside execute(). execute_with_packages() uses a separate two-step
    approach: first install packages into a temporary image layer using
    a network-enabled container, then run the script in the isolated
    container using that layer. This preserves network isolation for
    the actual script execution while still allowing package resolution.
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

        The container runs with --network none, so no outbound
        network access is possible during script execution.
        """
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', dir='/tmp', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        start_time = time.time()
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

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout + 5  # +5s for Docker overhead
            )

            execution_time = time.time() - start_time
            return ExecutionResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                timed_out=False
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            logger.warning(f"Execution timed out after {self.timeout}s")
            self._force_cleanup()
            return ExecutionResult(
                return_code=-1,
                stdout="",
                stderr=f"TimeoutError: Execution exceeded {self.timeout}s",
                execution_time=execution_time,
                timed_out=True,
                error_type="TimeoutError"
            )

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def execute_with_packages(
        self, code: str, packages: list[str]
    ) -> ExecutionResult:
        """
        Execute code after installing required packages.

        Used by the Code Debugging service's self-correction loop
        when ModuleNotFoundError is detected. The packages list
        typically comes from Schema B's pending_installs field.

        Two-step approach to preserve network isolation for script
        execution:
          Step 1 — Build a temporary image that extends agent-sandbox
                   with the required packages installed (network
                   enabled, no code executed).
          Step 2 — Run the script using that temporary image with
                   --network none (same isolation as execute()).

        The temporary image is removed after execution regardless of
        outcome.

        Args:
            code:     Python source code to execute.
            packages: List of pip-format package specs (e.g.,
                      ["yfinance==0.2.31", "pandas>=2.0"]).

        Returns:
            ExecutionResult from the isolated execution step.
        """
        if not packages:
            return self.execute(code)

        tmp_image = f"{self.IMAGE_NAME}-pkgs-{int(time.time())}"

        # --- Step 1: install packages into a temporary image layer ---
        pip_args = " ".join(packages)
        dockerfile_content = (
            f"FROM {self.IMAGE_NAME}\n"
            f"RUN pip install --no-cache-dir {pip_args}\n"
        )

        with tempfile.TemporaryDirectory() as build_dir:
            dockerfile_path = os.path.join(build_dir, "Dockerfile")
            with open(dockerfile_path, "w") as f:
                f.write(dockerfile_content)

            build_result = subprocess.run(
                ["docker", "build", "-t", tmp_image, build_dir],
                capture_output=True, text=True, timeout=300
            )

        if build_result.returncode != 0:
            logger.error(
                "Package installation failed:\n%s", build_result.stderr
            )
            return ExecutionResult(
                return_code=1,
                stdout="",
                stderr=(
                    f"PackageInstallError: Failed to install "
                    f"{packages}.\n{build_result.stderr}"
                ),
                execution_time=0.0,
                timed_out=False,
                error_type="PackageInstallError"
            )

        # --- Step 2: run the script in the isolated image ---
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', dir='/tmp', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        start_time = time.time()
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
                tmp_image,
                "python3", "/sandbox/script.py"
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.timeout + 5
            )

            execution_time = time.time() - start_time
            return ExecutionResult(
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time=execution_time,
                timed_out=False
            )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            self._force_cleanup(image=tmp_image)
            return ExecutionResult(
                return_code=-1,
                stdout="",
                stderr=f"TimeoutError: Execution exceeded {self.timeout}s",
                execution_time=execution_time,
                timed_out=True,
                error_type="TimeoutError"
            )

        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            # Always remove the temporary image
            subprocess.run(
                ["docker", "rmi", "--force", tmp_image],
                capture_output=True, timeout=15
            )

    def _force_cleanup(self, image: str = None):
        """
        Kill any running containers from the given image (or the
        default sandbox image). Called on timeout to prevent
        orphaned containers consuming resources.
        """
        target_image = image or self.IMAGE_NAME
        try:
            ps_result = subprocess.run(
                [
                    "docker", "ps", "-q",
                    "--filter", f"ancestor={target_image}"
                ],
                capture_output=True, text=True, timeout=5
            )
            container_ids = ps_result.stdout.strip().splitlines()
            if container_ids:
                subprocess.run(
                    ["docker", "kill"] + container_ids,
                    capture_output=True, timeout=10
                )
                logger.info(
                    "Force-killed %d container(s) from image %s",
                    len(container_ids), target_image
                )
        except Exception as e:
            logger.warning("Force cleanup failed: %s", e)
