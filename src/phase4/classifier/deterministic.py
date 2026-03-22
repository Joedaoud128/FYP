from __future__ import annotations

from phase4.domain.models import ClassificationResult, ErrorRecord, ErrorType, RuleId


class DeterministicPythonErrorClassifier:
    def classify(self, error: ErrorRecord) -> ClassificationResult:
        name = error.exception_name
        message = error.message

        if name == "ModuleNotFoundError":
            return ClassificationResult(
                rule_id=RuleId.MODULE_NOT_FOUND,
                error_type=ErrorType.MODULE_NOT_FOUND,
                module_name=error.module_name,
                source_file=error.source_file,
                line_number=error.line_number,
                missing_path=error.missing_path,
                diagnostic_message=message,
                confidence=1.0,
                reason="Python raised ModuleNotFoundError.",
            )

        if name == "ImportError" and "No module named" in message:
            return ClassificationResult(
                rule_id=RuleId.IMPORT_NO_MODULE,
                error_type=ErrorType.IMPORT_ERROR,
                module_name=error.module_name,
                source_file=error.source_file,
                line_number=error.line_number,
                missing_path=error.missing_path,
                diagnostic_message=message,
                confidence=0.95,
                reason="ImportError indicates missing module import.",
            )

        if name == "SyntaxError":
            return ClassificationResult(
                rule_id=RuleId.SYNTAX_ERROR,
                error_type=ErrorType.SYNTAX_ERROR,
                module_name=None,
                source_file=error.source_file,
                line_number=error.line_number,
                missing_path=error.missing_path,
                diagnostic_message=message,
                confidence=1.0,
                reason="Python raised SyntaxError.",
            )

        if name == "IndentationError":
            return ClassificationResult(
                rule_id=RuleId.INDENTATION_ERROR,
                error_type=ErrorType.INDENTATION_ERROR,
                module_name=None,
                source_file=error.source_file,
                line_number=error.line_number,
                missing_path=error.missing_path,
                diagnostic_message=message,
                confidence=1.0,
                reason="Python raised IndentationError.",
            )

        if name == "FileNotFoundError":
            return ClassificationResult(
                rule_id=RuleId.FILE_NOT_FOUND,
                error_type=ErrorType.FILE_NOT_FOUND,
                module_name=None,
                source_file=error.source_file,
                line_number=error.line_number,
                missing_path=error.missing_path,
                diagnostic_message=message,
                confidence=1.0,
                reason="Python raised FileNotFoundError.",
            )

        return ClassificationResult(
            rule_id=RuleId.OTHER,
            error_type=ErrorType.OTHER,
            module_name=None,
            source_file=error.source_file,
            line_number=error.line_number,
            missing_path=error.missing_path,
            diagnostic_message=message,
            confidence=0.5,
            reason=f"Unsupported exception type: {name}.",
        )
