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
    ILlmFallbackExecutor,
    ILlmFixProvider,
    IdempotencyPolicy,
)
from phase4.domain.models import (
    ActionStatus,
    ClassificationResult,
    ErrorRecord,
    IterationLog,
    JournalRecord,
    LlmFallbackRequest,
    Phase4PolicyConfig,
    PolicyDecision,
    WorkflowResult,
)
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
        llm_fix_provider: ILlmFixProvider | None = None,
        llm_fallback_executor: ILlmFallbackExecutor | None = None,
        fallback_session_id: str = "phase4_debug_session",
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
        self._llm_fix_provider = llm_fix_provider
        self._llm_fallback_executor = llm_fallback_executor
        self._fallback_session_id = fallback_session_id
        self._policy_config = policy_config or default_policy_config()
        self._confidence_gate = confidence_gate or ThresholdConfidenceGate(self._policy_config)
        self._idempotency_policy = idempotency_policy or InMemoryIdempotencyPolicy()
        self._action_journal = action_journal or JsonlActionJournal(str(self._policy_config.journal_path))
        self._max_iterations = max_iterations
        self._run_timeout_seconds = run_timeout_seconds

    def run(self, command: list[str]) -> WorkflowResult:
        logs: list[IterationLog] = []
        llm_fallback_used = False

        for attempt in range(1, self._max_iterations + 1):
            execution = self._execution_engine.run(command, timeout_seconds=self._run_timeout_seconds)
            if execution.exit_code == 0 and execution.stderr.strip() == "":
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
                    llm_fallback_used=llm_fallback_used,
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
                fallback_result = self._try_llm_fallback(
                    command=command,
                    attempt=attempt,
                    execution=execution,
                    parsed_error=None,
                    classification=None,
                    failure_reason="Command failed without parseable stderr output.",
                )
                if fallback_result is not None:
                    llm_fallback_used = True
                    logs.append(
                        IterationLog(
                            attempt=attempt,
                            execution=execution,
                            parsed_error=None,
                            classification=None,
                            action=None,
                            action_result=fallback_result,
                        )
                    )
                    if fallback_result.exit_code == 0:
                        continue
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Command failed without parseable stderr output.",
                    llm_fallback_used=llm_fallback_used,
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
                fallback_result = self._try_llm_fallback(
                    command=command,
                    attempt=attempt,
                    execution=execution,
                    parsed_error=parsed_error,
                    classification=classification,
                    failure_reason="Classification confidence below policy threshold.",
                )
                if fallback_result is not None:
                    llm_fallback_used = True
                    logs.append(
                        IterationLog(
                            attempt=attempt,
                            execution=execution,
                            parsed_error=parsed_error,
                            classification=classification,
                            action=None,
                            action_result=fallback_result,
                        )
                    )
                    if fallback_result.exit_code == 0:
                        continue
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Classification confidence below policy threshold.",
                    llm_fallback_used=llm_fallback_used,
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
                fallback_result = self._try_llm_fallback(
                    command=command,
                    attempt=attempt,
                    execution=execution,
                    parsed_error=parsed_error,
                    classification=classification,
                    failure_reason="No deterministic corrective action available.",
                )
                if fallback_result is not None:
                    llm_fallback_used = True
                    logs.append(
                        IterationLog(
                            attempt=attempt,
                            execution=execution,
                            parsed_error=parsed_error,
                            classification=classification,
                            action=None,
                            action_result=fallback_result,
                        )
                    )
                    if fallback_result.exit_code == 0:
                        continue
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="No deterministic corrective action available.",
                    llm_fallback_used=llm_fallback_used,
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
                fallback_result = self._try_llm_fallback(
                    command=command,
                    attempt=attempt,
                    execution=execution,
                    parsed_error=parsed_error,
                    classification=classification,
                    failure_reason="Repeated corrective action blocked by idempotency policy.",
                )
                if fallback_result is not None:
                    llm_fallback_used = True
                    logs.append(
                        IterationLog(
                            attempt=attempt,
                            execution=execution,
                            parsed_error=parsed_error,
                            classification=classification,
                            action=action,
                            action_result=fallback_result,
                        )
                    )
                    if fallback_result.exit_code == 0:
                        continue
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Repeated corrective action blocked by idempotency policy.",
                    llm_fallback_used=llm_fallback_used,
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
                fallback_result = self._try_llm_fallback(
                    command=command,
                    attempt=attempt,
                    execution=execution,
                    parsed_error=parsed_error,
                    classification=classification,
                    failure_reason="Corrective action execution failed.",
                )
                if fallback_result is not None:
                    llm_fallback_used = True
                    logs.append(
                        IterationLog(
                            attempt=attempt,
                            execution=execution,
                            parsed_error=parsed_error,
                            classification=classification,
                            action=action,
                            action_result=fallback_result,
                        )
                    )
                    if fallback_result.exit_code == 0:
                        continue
                return WorkflowResult(
                    success=False,
                    attempts=attempt,
                    final_execution=execution,
                    logs=logs,
                    failure_reason="Corrective action execution failed.",
                    llm_fallback_used=llm_fallback_used,
                )

        final_execution = logs[-1].execution
        return WorkflowResult(
            success=False,
            attempts=self._max_iterations,
            final_execution=final_execution,
            logs=logs,
            failure_reason="Unable to fix after max iterations.",
            llm_fallback_used=llm_fallback_used,
        )

    def _try_llm_fallback(
        self,
        command: list[str],
        attempt: int,
        execution,
        parsed_error: ErrorRecord | None,
        classification: ClassificationResult | None,
        failure_reason: str,
    ):
        if self._llm_fix_provider is None or self._llm_fallback_executor is None or parsed_error is None:
            return None

        request = LlmFallbackRequest(
            session_id=self._fallback_session_id,
            command=command,
            attempt=attempt,
            error=parsed_error,
            classification=classification,
            failure_reason=failure_reason,
        )
        response = self._llm_fix_provider.suggest_action(request)
        if not response.accepted or response.plan is None:
            self._record_journal(
                attempt=attempt,
                error_fingerprint=None,
                action_fingerprint=None,
                rule_id=classification.rule_id.value if classification is not None else None,
                confidence=classification.confidence if classification is not None else None,
                decision=PolicyDecision.ALLOW,
                action_type="llm_unrestricted_plan",
                status=ActionStatus.SKIPPED,
                execution_exit_code=execution.exit_code,
                action_exit_code=None,
                message=response.rejection_reason or "LLM fallback did not return a valid plan.",
            )
            return None

        fallback_result = self._llm_fallback_executor.execute_plan(response.plan)
        self._record_journal(
            attempt=attempt,
            error_fingerprint=None,
            action_fingerprint=None,
            rule_id=classification.rule_id.value if classification is not None else None,
            confidence=classification.confidence if classification is not None else None,
            decision=PolicyDecision.ALLOW,
            action_type="llm_unrestricted_plan",
            status=ActionStatus.EXECUTED if fallback_result.exit_code == 0 else ActionStatus.FAILED,
            execution_exit_code=execution.exit_code,
            action_exit_code=fallback_result.exit_code,
            message=fallback_result.stderr if fallback_result.exit_code != 0 else fallback_result.stdout,
        )
        return fallback_result

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
