from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.actions.executor import GuardedActionExecutor
from phase4.actions.planner import DeterministicActionPlanner
from phase4.classifier.deterministic import DeterministicPythonErrorClassifier
from phase4.parsing.stderr_parser import PythonStderrParser
from phase4.runtime.subprocess_engine import SubprocessExecutionEngine
from phase4.workflow.reactive import ReactiveDebugWorkflow


def _ensure_virtual_environment(venv_dir: Path) -> Path:
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)

    python_executable = venv_dir / "Scripts" / "python.exe"
    if not python_executable.exists():
        raise FileNotFoundError(f"Virtual environment Python not found: {python_executable}")
    return python_executable


def run_demo() -> int:
    venv_dir = Path(tempfile.mkdtemp(prefix="phase4_demo_venv_"))
    python_executable = _ensure_virtual_environment(venv_dir)

    workflow = ReactiveDebugWorkflow(
        execution_engine=SubprocessExecutionEngine(),
        parser=PythonStderrParser(),
        classifier=DeterministicPythonErrorClassifier(),
        action_planner=DeterministicActionPlanner(str(python_executable)),
        action_executor=GuardedActionExecutor(SubprocessExecutionEngine()),
        max_iterations=2,
        run_timeout_seconds=30,
    )

    command = [str(python_executable), "-c", "import yfinance; print(yfinance.__version__)"]
    result = workflow.run(command)

    summary = {
        "success": result.success,
        "attempts": result.attempts,
        "failure_reason": result.failure_reason,
        "logs": [
            {
                "attempt": log.attempt,
                "exit_code": log.execution.exit_code,
                "classified_error": None if log.classification is None else log.classification.error_type.value,
                "module_name": None if log.classification is None else log.classification.module_name,
                "action": None if log.action is None else log.action.command,
                "action_exit_code": None if log.action_result is None else log.action_result.exit_code,
            }
            for log in result.logs
        ],
    }

    print(json.dumps(summary, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(run_demo())
