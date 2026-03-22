from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from phase4.actions.executor import GuardedActionExecutor
from phase4.actions.llm_executor import UnrestrictedLlmFallbackExecutor
from phase4.actions.planner import DeterministicActionPlanner
from phase4.classifier.deterministic import DeterministicPythonErrorClassifier
from phase4.domain.models import Phase4PolicyConfig, WorkflowResult
from phase4.llm.local_provider import LocalLlmProvider
from phase4.parsing.stderr_parser import PythonStderrParser
from phase4.runtime.ollama_client import OllamaClient
from phase4.runtime.session_manager import PHASE4_SESSION_ID
from phase4.runtime.shared_runtime import SharedModelRuntime
from phase4.runtime.subprocess_engine import SubprocessExecutionEngine
from phase4.workflow.policy import default_policy_config
from phase4.workflow.reactive import ReactiveDebugWorkflow


@dataclass(frozen=True)
class SelfCorrectionOutcome:
    success: bool
    attempts: int
    failure_reason: str | None
    final_exit_code: int
    final_stderr: str


class SelfCorrectionService:
    def __init__(
        self,
        python_executable: str | None = None,
        workspace_root: str | None = None,
        policy_config: Phase4PolicyConfig | None = None,
        use_llm_fallback: bool = True,
        ollama_base_url: str = "http://localhost:11434",
        ollama_model: str = "llama3.2",
        max_iterations: int = 3,
        run_timeout_seconds: int = 30,
    ) -> None:
        self._python_executable = python_executable or sys.executable
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self._policy_config = policy_config or default_policy_config(str(self._workspace_root))
        self._use_llm_fallback = use_llm_fallback
        self._ollama_base_url = ollama_base_url
        self._ollama_model = ollama_model
        self._max_iterations = max_iterations
        self._run_timeout_seconds = run_timeout_seconds

    def is_runtime_healthy(self) -> bool:
        if not self._use_llm_fallback:
            return True
        return self._get_shared_ollama_client().health_check()

    def run_target_file(self, target_file: str) -> WorkflowResult:
        target_path = Path(target_file).resolve()
        command = [self._python_executable, str(target_path)]
        return self.run_command(command)

    def run_command(self, command: list[str]) -> WorkflowResult:
        execution_engine = SubprocessExecutionEngine()
        llm_provider = LocalLlmProvider(self._get_shared_ollama_client()) if self._use_llm_fallback else None
        llm_executor = UnrestrictedLlmFallbackExecutor(execution_engine=execution_engine)
        workflow = ReactiveDebugWorkflow(
            execution_engine=execution_engine,
            parser=PythonStderrParser(),
            classifier=DeterministicPythonErrorClassifier(),
            action_planner=DeterministicActionPlanner(
                python_executable=self._python_executable,
                workspace_root=str(self._workspace_root),
                file_creation_allowlist=self._policy_config.file_creation_allowlist,
            ),
            action_executor=GuardedActionExecutor(
                execution_engine=execution_engine,
                python_executable=self._python_executable,
            ),
            llm_fix_provider=llm_provider,
            llm_fallback_executor=llm_executor,
            fallback_session_id=PHASE4_SESSION_ID,
            policy_config=self._policy_config,
            max_iterations=self._max_iterations,
            run_timeout_seconds=self._run_timeout_seconds,
        )
        return workflow.run(command)

    @staticmethod
    def to_outcome(result: WorkflowResult) -> SelfCorrectionOutcome:
        return SelfCorrectionOutcome(
            success=result.success,
            attempts=result.attempts,
            failure_reason=result.failure_reason,
            final_exit_code=result.final_execution.exit_code,
            final_stderr=result.final_execution.stderr,
        )

    def _get_shared_ollama_client(self) -> OllamaClient:
        return SharedModelRuntime.get_ollama_client(
            base_url=self._ollama_base_url,
            model=self._ollama_model,
            timeout_seconds=self._run_timeout_seconds,
            max_concurrent_requests=1,
        )
