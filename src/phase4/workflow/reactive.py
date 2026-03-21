from __future__ import annotations

from datetime import datetime, timezone

from phase4.domain.interfaces import (
    ActionJournal,
    ConfidenceGate,
    CorrectiveActionExecutor,
    CorrectiveActionPlanner,
    ErrorClassifier,
    ErrorOutputParser,
    ExecutionEngine,
    IdempotencyPolicy,
)
from phase4.domain.models import ActionStatus, IterationLog, JournalRecord, Phase4PolicyConfig, PolicyDecision, WorkflowResult
from phase4.runtime.jsonl_journal import JsonlActionJournal
from phase4.workflow.fingerprints import build_action_fingerprint, build_error_fingerprint
from phase4.workflow.idempotency import InMemoryIdempotencyPolicy
from phase4.workflow.policy import ThresholdConfidenceGate, default_policy_config


class ReactiveDebugWorkflow:
    def __init__(
        self,
        execution_engine: ExecutionEngine,
        parser: ErrorOutputParser,
        classifier: ErrorClassifier,
        action_planner: CorrectiveActionPlanner,
        action_executor: CorrectiveActionExecutor,
        policy_config: Phase4PolicyConfig | None = None,
        confidence_gate: ConfidenceGate | None = None,
        idempotency_policy: IdempotencyPolicy | None = None,
        action_journal: ActionJournal | None = None,
        max_iterations: int = 3,
        run_timeout_seconds: int = 30,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        self._execution_engine = execution_engine
        self._parser = parser
        self._classifier = classifier
        self._action_planner = action_planner
        self._action_executor = action_executor
        self._policy_config = policy_config or default_policy_config()
        self._confidence_gate = confidence_gate or ThresholdConfidenceGate(self._policy_config)
        self._idempotency_policy = idempotency_policy or InMemoryIdempotencyPolicy()
        self._action_journal = action_journal or JsonlActionJournal(str(self._policy_config.journal_path))
        self._max_iterations = max_iterations
        self._run_timeout_seconds = run_timeout_seconds

    def run(self, command: list[str]) -> WorkflowResult:
        logs: list[IterationLog] = []

        for attempt in range(1, self._max_iterations + 1):
            execution = self._execution_engine.run(command, timeout_seconds=self._run_timeout_seconds)
            if execution.exit_code == 0:
                logs.append(
                    IterationLog(
                        attempt=attempt,
                        execution=execution,
                        parsed_error=None,
                        classification=None,
                        action=None,
                        action_result=None,
                    )
                )
                self._record_journal(
                    attempt=attempt,
                    error_fingerprint=None,
                    action_fingerprint=None,
                    rule_id=None,
                    confidence=None,
                    decision=PolicyDecision.ALLOW,
                    action_type=None,
                    status=ActionStatus.SKIPPED,
                    execution_exit_code=execution.exit_code,
                    action_exit_code=None,
                    message="Command executed successfully.",
                )
                return WorkflowResult(
                    success=True,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                )

            parsed_error = self._parser.parse(execution)
            if parsed_error is None:
                logs.append(
                    IterationLog(
                        attempt=attempt,
                        execution=execution,
                        parsed_error=None,
                        classification=None,
                        action=None,
                        action_result=None,
                    )
                )
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Command failed without parseable stderr output.",
                )

            classification = self._classifier.classify(parsed_error)
            decision = self._confidence_gate.evaluate(classification)
            if decision == PolicyDecision.DENY:
                logs.append(
                    IterationLog(
                        attempt=attempt,
                        execution=execution,
                        parsed_error=parsed_error,
                        classification=classification,
                        action=None,
                        action_result=None,
                    )
                )
                self._record_journal(
                    attempt=attempt,
                    error_fingerprint=build_error_fingerprint(parsed_error, classification),
                    action_fingerprint=None,
                    rule_id=classification.rule_id.value,
                    confidence=classification.confidence,
                    decision=decision,
                    action_type=None,
                    status=ActionStatus.SKIPPED,
                    execution_exit_code=execution.exit_code,
                    action_exit_code=None,
                    message="Confidence gate denied auto-remediation.",
                )
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Classification confidence below policy threshold.",
                )

            action = self._action_planner.plan(classification)

            if action is None:
                logs.append(
                    IterationLog(
                        attempt=attempt,
                        execution=execution,
                        parsed_error=parsed_error,
                        classification=classification,
                        action=None,
                        action_result=None,
                    )
                )
                self._record_journal(
                    attempt=attempt,
                    error_fingerprint=build_error_fingerprint(parsed_error, classification),
                    action_fingerprint=None,
                    rule_id=classification.rule_id.value,
                    confidence=classification.confidence,
                    decision=decision,
                    action_type=None,
                    status=ActionStatus.SKIPPED,
                    execution_exit_code=execution.exit_code,
                    action_exit_code=None,
                    message="No deterministic corrective action available.",
                )
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="No deterministic corrective action available.",
                )

            error_fingerprint = build_error_fingerprint(parsed_error, classification)
            action_fingerprint = build_action_fingerprint(action)

            if self._idempotency_policy.should_block(error_fingerprint, action_fingerprint):
                logs.append(
                    IterationLog(
                        attempt=attempt,
                        execution=execution,
                        parsed_error=parsed_error,
                        classification=classification,
                        action=action,
                        action_result=None,
                    )
                )
                self._record_journal(
                    attempt=attempt,
                    error_fingerprint=error_fingerprint,
                    action_fingerprint=action_fingerprint,
                    rule_id=classification.rule_id.value,
                    confidence=classification.confidence,
                    decision=decision,
                    action_type=action.action_type.value,
                    status=ActionStatus.SKIPPED,
                    execution_exit_code=execution.exit_code,
                    action_exit_code=None,
                    message="Idempotency policy blocked repeated action.",
                )
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Repeated corrective action blocked by idempotency policy.",
                )

            self._idempotency_policy.remember(error_fingerprint, action_fingerprint)

            action_result = self._action_executor.execute(action)
            logs.append(
                IterationLog(
                    attempt=attempt,
                    execution=execution,
                    parsed_error=parsed_error,
                    classification=classification,
                    action=action,
                    action_result=action_result,
                )
            )
            self._record_journal(
                attempt=attempt,
                error_fingerprint=error_fingerprint,
                action_fingerprint=action_fingerprint,
                rule_id=classification.rule_id.value,
                confidence=classification.confidence,
                decision=decision,
                action_type=action.action_type.value,
                status=ActionStatus.EXECUTED if action_result.exit_code == 0 else ActionStatus.FAILED,
                execution_exit_code=execution.exit_code,
                action_exit_code=action_result.exit_code,
                message=action_result.stderr if action_result.exit_code != 0 else action_result.stdout,
            )

            if action_result.exit_code != 0:
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Corrective action execution failed.",
                )

        final_execution = logs[-1].execution
        return WorkflowResult(
            success=False,
            attempts=self._max_iterations,
            final_execution=final_execution,
            logs=logs,
            failure_reason="Unable to fix after max iterations.",
        )

    def _record_journal(
        self,
        attempt: int,
        error_fingerprint: str | None,
        action_fingerprint: str | None,
        rule_id: str | None,
        confidence: float | None,
        decision: PolicyDecision,
        action_type: str | None,
        status: ActionStatus,
        execution_exit_code: int | None,
        action_exit_code: int | None,
        message: str,
    ) -> None:
        entry = JournalRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            attempt=attempt,
            error_fingerprint=error_fingerprint,
            action_fingerprint=action_fingerprint,
            rule_id=rule_id,
            confidence=confidence,
            policy_decision=decision.value,
            action_type=action_type,
            action_status=status,
            execution_exit_code=execution_exit_code,
            action_exit_code=action_exit_code,
            message=message,
        )
        self._action_journal.record(entry)
