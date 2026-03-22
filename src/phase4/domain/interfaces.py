from __future__ import annotations

from typing import Protocol

from phase4.domain.models import (
    ClassificationResult,
    CorrectiveAction,
    ErrorRecord,
    ExecutionResult,
    GuardrailDecision,
    JournalRecord,
    LlmFallbackPlan,
    LlmFallbackRequest,
    LlmFallbackResponse,
    LlmProposal,
    PolicyDecision,
)


class ExecutionEngine(Protocol):
    def run(self, command: list[str], timeout_seconds: int | None = None) -> ExecutionResult:
        ...


class ErrorOutputParser(Protocol):
    def parse(self, execution_result: ExecutionResult) -> ErrorRecord | None:
        ...


class ErrorClassifier(Protocol):
    def classify(self, error: ErrorRecord) -> ClassificationResult:
        ...


class CorrectiveActionPlanner(Protocol):
    def plan(self, classification: ClassificationResult) -> CorrectiveAction | None:
        ...


class CorrectiveActionExecutor(Protocol):
    def execute(self, action: CorrectiveAction) -> ExecutionResult:
        ...


class ConfidenceGate(Protocol):
    def evaluate(self, classification: ClassificationResult) -> PolicyDecision:
        ...


class IdempotencyPolicy(Protocol):
    def should_block(self, error_fingerprint: str, action_fingerprint: str) -> bool:
        ...

    def remember(self, error_fingerprint: str, action_fingerprint: str) -> None:
        ...


class ActionJournal(Protocol):
    def record(self, entry: JournalRecord) -> None:
        ...


class LlmRemediationProvider(Protocol):
    def generate(
        self,
        command: list[str],
        execution_result: ExecutionResult,
        parsed_error: ErrorRecord | None,
        classification: ClassificationResult | None,
    ) -> LlmProposal | None:
        ...


class LlmProposalGuard(Protocol):
    def evaluate_command(self, command: list[str]) -> GuardrailDecision:
        ...


class LlmRemediator(Protocol):
    def remediate(
        self,
        command: list[str],
        execution_result: ExecutionResult,
        parsed_error: ErrorRecord | None,
        classification: ClassificationResult | None,
    ) -> ExecutionResult:
        ...


class ILlmFixProvider(Protocol):
    def suggest_action(self, request: LlmFallbackRequest) -> LlmFallbackResponse:
        ...


class ILlmFallbackExecutor(Protocol):
    def execute_plan(self, plan: LlmFallbackPlan) -> ExecutionResult:
        ...
