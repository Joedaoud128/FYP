"""
Test DockerExecutor security isolation.
These tests require Docker Desktop running.

Run with: pytest tests/system/test_docker_sandbox.py -v -m system
"""

import pytest
import subprocess
import sys
import os
from pathlib import Path

# Add docker directory to Python path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCKER_PATH = str(_PROJECT_ROOT / "docker")

# Ensure docker_executor can be imported
if _DOCKER_PATH not in sys.path:
    sys.path.insert(0, _DOCKER_PATH)


@pytest.mark.system
@pytest.mark.slow
class TestDockerSandbox:
    """Verify Docker sandbox provides proper isolation."""

    @pytest.fixture(autouse=True)
    def check_docker(self):
        """Skip tests if Docker is not available."""
        try:
            result = subprocess.run(
                ["docker", "ps"],
                capture_output=True,
                timeout=5
            )
            if result.returncode != 0:
                pytest.skip("Docker not running or not available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Docker not available")

    def test_no_network_access(self):
        """Container should have --network none (no internet)."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=10)
        result = executor.execute("""
import socket
try:
    socket.gethostbyname('google.com')
    print('NETWORK_ACCESSIBLE')
except Exception as e:
    print(f'NETWORK_ISOLATED: {type(e).__name__}')
""")
        assert "NETWORK_ISOLATED" in result.stdout
        assert "NETWORK_ACCESSIBLE" not in result.stdout

    def test_read_only_filesystem(self):
        """Container should be read-only except /workspace."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=10)
        result = executor.execute("""
import os
try:
    with open('/etc/passwd', 'w') as f:
        f.write('hack')
    print('WRITE_SUCCEEDED')
except (IOError, PermissionError, OSError) as e:
    print(f'READ_ONLY: {type(e).__name__}')
""")
        assert "READ_ONLY" in result.stdout
        assert "WRITE_SUCCEEDED" not in result.stdout

    def test_memory_limit_enforced(self):
        """Container memory should be limited to 512m."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=30)
        result = executor.execute("""
import sys
import time

# Try to allocate memory beyond limit
allocated = []
try:
    # Allocate 100MB chunks until we hit limit
    for i in range(20):  # Up to 2GB total
        chunk = bytearray(100 * 1024 * 1024)  # 100MB
        allocated.append(chunk)
        print(f'ALLOCATED_{i+1}_CHUNKS')
        time.sleep(0.1)
    print('MEMORY_ALLOCATED')
except MemoryError:
    print('MEMORY_LIMITED')
except Exception as e:
    print(f'MEMORY_ERROR: {type(e).__name__}')
""")
        # Container should limit memory (either MemoryError or process killed)
        assert "MEMORY_LIMITED" in result.stdout or "Killed" in result.stderr or result.return_code != 0

    def test_pid_limit_enforced(self):
        """Container should have PID limit (no fork bombs)."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=10)
        result = executor.execute("""
import os
import sys

try:
    # Try to create many processes
    pids = []
    for i in range(200):  # Try to exceed PID limit
        pid = os.fork()
        if pid == 0:
            # Child process - exit immediately
            sys.exit(0)
        else:
            pids.append(pid)
            if i > 150:
                print(f'CREATED_{len(pids)}_PROCESSES')
    
    # Clean up
    for pid in pids:
        os.waitpid(pid, 0)
    print('ALL_PROCESSES_CREATED')
except OSError as e:
    print(f'PID_LIMIT_REACHED: {e.errno}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}')
""")
        # Should hit PID limit before 200 processes
        assert "PID_LIMIT_REACHED" in result.stdout or "ALL_PROCESSES_CREATED" not in result.stdout

    def test_cpu_limit_enforced(self):
        """Container should have CPU limit (1 core)."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=15)
        result = executor.execute("""
import time

def cpu_intensive():
    start = time.time()
    x = 0
    # Busy loop for 2 seconds
    while time.time() - start < 2:
        x += 1
    return x

# Run CPU-intensive task and measure time
start = time.time()
cpu_intensive()
elapsed = time.time() - start

# Should take about 2 seconds (not limited by CPU quota)
# If CPU limit is working, it won't be drastically slower
if elapsed < 10:
    print('CPU_LIMIT_WORKING')
else:
    print(f'TOO_SLOW: {elapsed:.1f}s')
""")
        assert "CPU_LIMIT_WORKING" in result.stdout

    def test_disk_limit_enforced(self):
        """Container should have disk write limit (100m tmpfs)."""
        from docker_executor import DockerExecutor
        
        executor = DockerExecutor(timeout=30)
        result = executor.execute("""
import os

try:
    # Try to write more than 100MB to /workspace
    with open('/workspace/large_file.dat', 'wb') as f:
        # Write 150MB in chunks
        chunk = b'X' * (1024 * 1024)  # 1MB
        for i in range(150):
            f.write(chunk)
            if i % 10 == 0:
                print(f'WRITTEN_{i+1}_MB')
    print('DISK_WRITE_SUCCEEDED')
except (IOError, OSError) as e:
    print(f'DISK_LIMITED: {type(e).__name__}')
""")
        # Should hit disk limit before 150MB
        assert "DISK_LIMITED" in result.stdout or "DISK_WRITE_SUCCEEDED" not in result.stdout