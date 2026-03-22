from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional


class ErrorType(str, Enum):
    MODULE_NOT_FOUND = "module_not_found"
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    INDENTATION_ERROR = "indentation_error"
    FILE_NOT_FOUND = "file_not_found"
    OTHER = "other"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    PIP_INSTALL = "pip_install"
    NORMALIZE_INDENTATION = "normalize_indentation"
    CREATE_MISSING_FILE = "create_missing_file"
    NO_OP = "no_op"


class RuleId(str, Enum):
    MODULE_NOT_FOUND = "rule_module_not_found"
    IMPORT_NO_MODULE = "rule_import_no_module"
    SYNTAX_ERROR = "rule_syntax_error"
    INDENTATION_ERROR = "rule_indentation_error"
    FILE_NOT_FOUND = "rule_file_not_found"
    OTHER = "rule_other"


class ActionStatus(str, Enum):
    SKIPPED = "skipped"
    EXECUTED = "executed"
    FAILED = "failed"


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class LlmProposalType(str, Enum):
    SCRIPT_PATCH = "script_patch"
    COMMAND = "command"


@dataclass(frozen=True)
class ExecutionResult:
    command: List[str]
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ErrorRecord:
    exception_name: str
    message: str
    raw_stderr: str
    module_name: Optional[str] = None
    source_file: Optional[str] = None
    line_number: Optional[int] = None
    missing_path: Optional[str] = None


@dataclass(frozen=True)
class ClassificationResult:
    rule_id: RuleId
    error_type: ErrorType
    module_name: Optional[str]
    source_file: Optional[str]
    line_number: Optional[int]
    missing_path: Optional[str]
    diagnostic_message: Optional[str]
    confidence: float
    reason: str


@dataclass(frozen=True)
class CorrectiveAction:
    action_type: ActionType
    command: Optional[List[str]]
    arguments: dict[str, Any]
    safe_to_auto_execute: bool
    description: str


@dataclass(frozen=True)
class GuardrailDecision:
    allowed: bool
    reason: str
    normalized_command: Optional[List[str]]


@dataclass(frozen=True)
class LlmProposal:
    proposal_type: LlmProposalType
    rationale: str
    target_file: Optional[str] = None
    script_content: Optional[str] = None
    command: Optional[List[str]] = None


@dataclass(frozen=True)
class LlmShellCommand:
    command: List[str]


@dataclass(frozen=True)
class LlmFileWrite:
    file_path: str
    content: str


@dataclass(frozen=True)
class LlmFallbackPlan:
    commands: List[LlmShellCommand] = field(default_factory=list)
    file_writes: List[LlmFileWrite] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass(frozen=True)
class LlmFallbackRequest:
    session_id: str
    command: List[str]
    attempt: int
    error: ErrorRecord
    classification: Optional[ClassificationResult]
    failure_reason: str


@dataclass(frozen=True)
class LlmFallbackResponse:
    plan: Optional[LlmFallbackPlan]
    raw_model_output: str
    accepted: bool
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class JournalRecord:
    timestamp_utc: str
    attempt: int
    error_fingerprint: Optional[str]
    action_fingerprint: Optional[str]
    rule_id: Optional[str]
    confidence: Optional[float]
    policy_decision: str
    action_type: Optional[str]
    action_status: ActionStatus
    execution_exit_code: Optional[int]
    action_exit_code: Optional[int]
    message: str


@dataclass(frozen=True)
class Phase4PolicyConfig:
    rule_thresholds: dict[RuleId, float]
    default_threshold: float
    file_creation_allowlist: tuple[str, ...]
    journal_path: Path


@dataclass(frozen=True)
class IterationLog:
    attempt: int
    execution: ExecutionResult
    parsed_error: Optional[ErrorRecord]
    classification: Optional[ClassificationResult]
    action: Optional[CorrectiveAction]
    action_result: Optional[ExecutionResult]


@dataclass(frozen=True)
class WorkflowResult:
    success: bool
    attempts: int
    final_execution: ExecutionResult
    logs: List[IterationLog] = field(default_factory=list)
    failure_reason: Optional[str] = None
    llm_fallback_used: bool = False
