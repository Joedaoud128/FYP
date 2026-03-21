from __future__ import annotations

import re
from pathlib import Path

from phase4.domain.models import ActionType, ClassificationResult, CorrectiveAction, ErrorType


class DeterministicActionPlanner:
    _SAFE_PACKAGE_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")

    def __init__(
        self,
        python_executable: str,
        workspace_root: str | None = None,
        file_creation_allowlist: tuple[str, ...] | None = None,
    ) -> None:
        self._python_executable = python_executable
        self._workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self._file_creation_allowlist = file_creation_allowlist or ()

    def plan(self, classification: ClassificationResult) -> CorrectiveAction | None:
        if classification.error_type in {ErrorType.MODULE_NOT_FOUND, ErrorType.IMPORT_ERROR}:
            return self._plan_install_action(classification)

        if classification.error_type in {ErrorType.SYNTAX_ERROR, ErrorType.INDENTATION_ERROR}:
            return self._plan_indentation_normalization(classification)

        if classification.error_type == ErrorType.FILE_NOT_FOUND:
            return self._plan_create_missing_file(classification)

        return None

    def _plan_install_action(self, classification: ClassificationResult) -> CorrectiveAction | None:
        module_name = classification.module_name
        if not module_name or not self._SAFE_PACKAGE_PATTERN.match(module_name):
            return None

        return CorrectiveAction(
            action_type=ActionType.PIP_INSTALL,
            command=[self._python_executable, "-m", "pip", "install", module_name],
            arguments={},
            safe_to_auto_execute=True,
            description=f"Install missing Python package '{module_name}'.",
        )

    def _plan_indentation_normalization(self, classification: ClassificationResult) -> CorrectiveAction | None:
        source_file = classification.source_file
        line_number = classification.line_number
        if source_file is None or line_number is None:
            return None

        if line_number < 1:
            return None

        resolved = self._resolve_safe_workspace_path(source_file)
        if resolved is None:
            return None

        return CorrectiveAction(
            action_type=ActionType.NORMALIZE_INDENTATION,
            command=None,
            arguments={"file_path": str(resolved), "line_number": line_number},
            safe_to_auto_execute=True,
            description=f"Normalize indentation for '{resolved.name}' at line {line_number}.",
        )

    def _plan_create_missing_file(self, classification: ClassificationResult) -> CorrectiveAction | None:
        missing_path = classification.missing_path
        if missing_path is None:
            return None

        resolved = self._resolve_safe_workspace_path(missing_path)
        if resolved is None:
            return None

        relative_path = resolved.relative_to(self._workspace_root).as_posix()
        if not any(relative_path.startswith(prefix.rstrip("/") + "/") or relative_path == prefix.rstrip("/") for prefix in self._file_creation_allowlist):
            return None

        if resolved.exists():
            return None

        return CorrectiveAction(
            action_type=ActionType.CREATE_MISSING_FILE,
            command=None,
            arguments={"file_path": str(resolved)},
            safe_to_auto_execute=True,
            description=f"Create missing file path '{resolved}'.",
        )

    def _resolve_safe_workspace_path(self, path_value: str) -> Path | None:
        candidate = Path(path_value)
        resolved = candidate.resolve() if candidate.is_absolute() else (self._workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            return None

        return resolved
