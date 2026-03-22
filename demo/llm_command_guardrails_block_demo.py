from __future__ import annotations

import json
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
from phase4.domain.models import LlmProposal, LlmProposalType
from phase4.llm.channel import LlmRemediationChannel
from phase4.llm.guardrails_gate import GuardrailsProposalGuard
from phase4.parsing.stderr_parser import PythonStderrParser
from phase4.runtime.subprocess_engine import SubprocessExecutionEngine
from phase4.workflow.reactive import ReactiveDebugWorkflow


class MockUnsafeCommandProvider:
    def generate(self, command, execution_result, parsed_error, classification):
        _ = command, execution_result, parsed_error, classification
        return LlmProposal(
            proposal_type=LlmProposalType.COMMAND,
            rationale="Unsafe remediation command for demo blocking.",
            command=["python", "-c", "print('unsafe')"],
        )


def run_demo() -> int:
    with tempfile.TemporaryDirectory(prefix="phase4_llm_guard_demo_") as tmp_dir:
        workspace = Path(tmp_dir)
        script = workspace / "broken.py"
        script.write_text("raise RuntimeError('boom')\n", encoding="utf-8")

        engine = SubprocessExecutionEngine()
        llm_channel = LlmRemediationChannel(
            provider=MockUnsafeCommandProvider(),
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
            run_timeout_seconds=30,
        )

        result = workflow.run([sys.executable, str(script)])

        summary = {
            "success": result.success,
            "attempts": result.attempts,
            "failure_reason": result.failure_reason,
            "llm_action_stderr": None if not result.logs or result.logs[0].action_result is None else result.logs[0].action_result.stderr,
        }
        print(json.dumps(summary, indent=2))
        return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(run_demo())
