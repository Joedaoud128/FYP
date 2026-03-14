"""
Docker-based sandboxed execution engine for the AI Coding Agent.
Replaces direct subprocess.run() with containerized execution.
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
    """Structured result from sandboxed execution."""
    return_code: int
    stdout: str
    stderr: str
    execution_time: float
    timed_out: bool
    error_type: Optional[str] = None


class DockerExecutor:
    """Executes Python code inside Docker containers."""

    # These match your guardrails document specifications
    DEFAULT_TIMEOUT = 30      # seconds per script
    MAX_TIMEOUT = 300         # absolute maximum
    MEMORY_LIMIT = "512m"     # 512MB RAM
    CPU_LIMIT = "1"           # 1 CPU core
    PID_LIMIT = "100"         # max 100 processes
    DISK_LIMIT = "100m"       # 100MB writable space
    IMAGE_NAME = "agent-sandbox"

    def __init__(self, timeout: int = None):
        self.timeout = min(
            timeout or self.DEFAULT_TIMEOUT,
            self.MAX_TIMEOUT
        )
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
            raise RuntimeError(
                "Docker is not installed or not in PATH."
            )

    def execute(self, code: str) -> ExecutionResult:
        """
        Execute Python code in a sandboxed container.

        Args:
            code: The Python source code string to execute.

        Returns:
            ExecutionResult with return_code, stdout, stderr,
            execution_time, and timed_out flag.
        """
        # --- Write code to a temporary file on the HOST ---
        # This temp file is mounted read-only into the container.
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py',
            dir='/tmp', delete=False
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            # --- Build the docker run command ---
            cmd = [
                "docker", "run",
                "--rm",                    # auto-cleanup
                "--network", "none",        # no internet
                "--memory", self.MEMORY_LIMIT,
                "--memory-swap", self.MEMORY_LIMIT,
                "--cpus", self.CPU_LIMIT,
                "--pids-limit", self.PID_LIMIT,
                "--read-only",              # read-only filesystem
                "--tmpfs", f"/workspace:rw,noexec,size={self.DISK_LIMIT}",
                "--cap-drop", "ALL",        # drop all capabilities
                "--security-opt", "no-new-privileges",
                # Mount the script read-only into the container
                "-v", f"{tmp_path}:/sandbox/script.py:ro",
                self.IMAGE_NAME,
                "python3", "/sandbox/script.py"
            ]

            logger.info(f"Executing in container (timeout={self.timeout}s)")
            start_time = time.time()

            # --- Run the container ---
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 5  # +5s grace for Docker overhead
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

            # Kill any lingering container
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
            # Always clean up the temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def execute_with_packages(
        self, code: str, packages: list[str]
    ) -> ExecutionResult:
        """
        Execute code after installing additional packages.
        Used by the self-correction loop when ModuleNotFoundError
        is detected and the fix is to pip install a library.
        """
        # Prepend pip install commands to the script
        install_lines = []
        for pkg in packages:
            install_lines.append(
                f"import subprocess; "
                f"subprocess.run(['pip', 'install', '{pkg}'], "
                f"capture_output=True)"
            )
        modified_code = "\n".join(install_lines) + "\n" + code
        return self.execute(modified_code)

    def _force_cleanup(self):
        """Kill any running containers from our image."""
        try:
            subprocess.run(
                ["docker", "ps", "-q", "--filter",
                 f"ancestor={self.IMAGE_NAME}"],
                capture_output=True, text=True, timeout=5
            )
        except Exception:
            pass  # Best effort cleanup
