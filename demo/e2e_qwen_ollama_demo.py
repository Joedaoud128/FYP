from __future__ import annotations

import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.actions.executor import GuardedActionExecutor
from phase4.actions.planner import DeterministicActionPlanner
from phase4.classifier.deterministic import DeterministicPythonErrorClassifier
from phase4.llm.channel import LlmRemediationChannel
from phase4.llm.guardrails_gate import GuardrailsProposalGuard
from phase4.llm.ollama_client import OllamaRemediationProvider
from phase4.parsing.stderr_parser import PythonStderrParser
from phase4.runtime.subprocess_engine import SubprocessExecutionEngine
from phase4.workflow.reactive import ReactiveDebugWorkflow


def _ollama_available(base_url: str = "http://127.0.0.1:11434") -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def run_demo() -> int:
    if not _ollama_available():
        print(json.dumps({
            "status": "skipped",
            "reason": "Ollama server not available on http://127.0.0.1:11434",
            "hint": "Run: ollama serve; ollama pull qwen3.5:0.8b-instruct-q4_K_M",
        }, indent=2))
        return 0

    with tempfile.TemporaryDirectory(prefix="phase4_qwen_demo_") as tmp_dir:
        workspace = Path(tmp_dir)
        script = workspace / "broken.py"
        script.write_text("raise RuntimeError('unknown branch for llm fallback')\n", encoding="utf-8")

        engine = SubprocessExecutionEngine()
        llm_channel = LlmRemediationChannel(
            provider=OllamaRemediationProvider(),
            guard=GuardrailsProposalGuard(workspace_root=str(workspace)),
            execution_engine=engine,
            workspace_root=str(workspace),
        )

        workflow = ReactiveDebugWorkflow(
            execution_engine=engine,
            parser=PythonStderrParser(),
            classifier=DeterministicPythonErrorClassifier(),
            action_planner=DeterministicActionPlanner(sys.executable, workspace_root=str(workspace)),
            action_executor=GuardedActionExecutor(engine, python_executable=sys.executable),
            llm_remediator=llm_channel,
            max_iterations=2,
            run_timeout_seconds=40,
        )

        result = workflow.run([sys.executable, str(script)])
        print(json.dumps({
            "status": "completed",
            "success": result.success,
            "attempts": result.attempts,
            "failure_reason": result.failure_reason,
            "logs": len(result.logs),
        }, indent=2))
        return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(run_demo())
