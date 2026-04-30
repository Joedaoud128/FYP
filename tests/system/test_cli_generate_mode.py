# tests/system/test_cli_generate_mode.py
"""
System tests for Generate Mode (--generate flag)
"""

import pytest
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CLI = str(_PROJECT_ROOT / "ESIB_AiCodingAgent.py")

def _run_cli(*args, timeout=120):
    return subprocess.run(
        [sys.executable, _CLI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(_PROJECT_ROOT),
    )

@pytest.mark.system
@pytest.mark.slow
class TestGenerateMode:
    """Test that Generate Mode produces working code."""

    def test_generate_simple_script(self, tmp_path):
        """Generate a simple script and verify it runs."""
        prompt = "Write a function that returns the sum of two numbers"
        proc = _run_cli("--generate", prompt, "--output", str(tmp_path / "output.py"), timeout=180)
        
        assert proc.returncode == 0
        assert (tmp_path / "output.py").exists()
        
        # Verify the generated script runs
        result = subprocess.run(
            [sys.executable, str(tmp_path / "output.py")],
            capture_output=True,
            text=True,
            timeout=10
        )
        assert result.returncode == 0

    def test_generate_fibonacci(self):
        """Generate Fibonacci sequence generator."""
        proc = _run_cli("--generate", "Write a function that returns the first 10 Fibonacci numbers", timeout=180)
        assert proc.returncode == 0
        assert "fibonacci" in proc.stdout.lower() or "success" in proc.stdout.lower()