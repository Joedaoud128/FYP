from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from phase4.domain.models import (
    ClassificationResult,
    ErrorType,
    ExecutionResult,
    GuardrailDecision,
    LlmProposal,
    LlmProposalType,
    RuleId,
)
from phase4.llm.channel import LlmRemediationChannel


class FakeProvider:
    def __init__(self, proposal: LlmProposal | None) -> None:
        self.proposal = proposal

    def generate(self, command, execution_result, parsed_error, classification):
        _ = command, execution_result, parsed_error, classification
        return self.proposal


class FakeGuard:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def evaluate_command(self, command: list[str]) -> GuardrailDecision:
        _ = command
        if self.allowed:
            return GuardrailDecision(allowed=True, reason="ALLOW", normalized_command=command)
        return GuardrailDecision(allowed=False, reason="BLOCK", normalized_command=None)


class FakeEngine:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        _ = timeout_seconds
        self.calls.append(command)
        is_compile = len(command) >= 3 and command[1:3] == ["-m", "py_compile"]
        if is_compile:
            return ExecutionResult(command=command, exit_code=0, stdout="", stderr="")
        return ExecutionResult(command=command, exit_code=0, stdout="ok", stderr="")


class TestLlmChannel(unittest.TestCase):
    def test_script_patch_is_applied_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workspace = Path(tmp_dir)
            script = workspace / "broken.py"
            script.write_text("raise RuntimeError('x')\n", encoding="utf-8")

            proposal = LlmProposal(
                proposal_type=LlmProposalType.SCRIPT_PATCH,
                rationale="fix",
                script_content="print('fixed')\n",
            )
            channel = LlmRemediationChannel(
                provider=FakeProvider(proposal),
                guard=FakeGuard(allowed=True),
                execution_engine=FakeEngine(),
                workspace_root=str(workspace),
            )

            result = channel.remediate(
                command=[sys.executable, str(script)],
                execution_result=ExecutionResult(command=[sys.executable, str(script)], exit_code=1, stdout="", stderr="err"),
                parsed_error=None,
                classification=None,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(script.read_text(encoding="utf-8"), "print('fixed')\n")

    def test_command_is_blocked_by_guardrails(self) -> None:
        proposal = LlmProposal(
            proposal_type=LlmProposalType.COMMAND,
            rationale="unsafe",
            command=["python", "-c", "print('x')"],
        )
        engine = FakeEngine()
        channel = LlmRemediationChannel(
            provider=FakeProvider(proposal),
            guard=FakeGuard(allowed=False),
            execution_engine=engine,
            workspace_root=str(PROJECT_ROOT),
        )

        result = channel.remediate(
            command=["python", "app.py"],
            execution_result=ExecutionResult(command=["python", "app.py"], exit_code=1, stdout="", stderr="err"),
            parsed_error=None,
            classification=ClassificationResult(
                rule_id=RuleId.OTHER,
                error_type=ErrorType.OTHER,
                module_name=None,
                source_file=None,
                line_number=None,
                missing_path=None,
                diagnostic_message="err",
                confidence=0.4,
                reason="other",
            ),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Guardrails blocked LLM command", result.stderr)
        self.assertEqual(len(engine.calls), 0)


if __name__ == "__main__":
    unittest.main()
