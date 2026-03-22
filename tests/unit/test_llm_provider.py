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
    ErrorRecord,
    ErrorType,
    LlmFallbackRequest,
    RuleId,
)
from phase4.llm.local_provider import LocalLlmProvider


class FakeOllamaClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def chat(self, session_id: str, user_message: str) -> str:
        _ = session_id
        _ = user_message
        return self._response


class TestLocalLlmProvider(unittest.TestCase):
    def _request(self) -> LlmFallbackRequest:
        return LlmFallbackRequest(
            session_id="phase4_debug_session",
            command=["python", "script.py"],
            attempt=1,
            error=ErrorRecord(
                exception_name="ModuleNotFoundError",
                message="No module named 'yfinance'",
                raw_stderr="ModuleNotFoundError: No module named 'yfinance'",
                module_name="yfinance",
            ),
            classification=ClassificationResult(
                rule_id=RuleId.MODULE_NOT_FOUND,
                error_type=ErrorType.MODULE_NOT_FOUND,
                module_name="yfinance",
                source_file=None,
                line_number=None,
                missing_path=None,
                diagnostic_message="No module named 'yfinance'",
                confidence=1.0,
                reason="test",
            ),
            failure_reason="No deterministic corrective action available.",
        )

    def test_provider_parses_command_plan(self) -> None:
        provider = LocalLlmProvider(
            FakeOllamaClient(
                '{"commands": [["python", "-m", "pip", "install", "yfinance"]], "notes": "install dependency"}'
            )
        )

        response = provider.suggest_action(self._request())

        self.assertTrue(response.accepted)
        self.assertIsNotNone(response.plan)
        assert response.plan is not None
        self.assertEqual(response.plan.commands[0].command, ["python", "-m", "pip", "install", "yfinance"])

    def test_provider_rejects_invalid_payload(self) -> None:
        provider = LocalLlmProvider(FakeOllamaClient("not-json"))

        response = provider.suggest_action(self._request())

        self.assertFalse(response.accepted)
        self.assertIsNone(response.plan)

    def test_provider_parses_file_write_from_fenced_json(self) -> None:
        provider = LocalLlmProvider(
            FakeOllamaClient(
                """```json
{
  \"file_writes\": [
    {
      \"file_path\": \"test.py\",
      \"content\": \"print('fixed')\\n\"
    }
  ]
}
```"""
            )
        )

        response = provider.suggest_action(self._request())

        self.assertTrue(response.accepted)
        self.assertIsNotNone(response.plan)
        assert response.plan is not None
        self.assertEqual(response.plan.file_writes[0].file_path, "test.py")

    def test_prompt_guidance_prefers_file_writes_for_syntax_error(self) -> None:
        provider = LocalLlmProvider(FakeOllamaClient('{"commands": [["python", "-V"]]}'))

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "bad.py"
            source_path.write_text('print("oops)\n', encoding="utf-8")

            request = LlmFallbackRequest(
                session_id="phase4_debug_session",
                command=["python", str(source_path)],
                attempt=1,
                error=ErrorRecord(
                    exception_name="SyntaxError",
                    message="unterminated string literal",
                    raw_stderr="SyntaxError: unterminated string literal",
                    source_file=str(source_path),
                    line_number=1,
                ),
                classification=ClassificationResult(
                    rule_id=RuleId.SYNTAX_ERROR,
                    error_type=ErrorType.SYNTAX_ERROR,
                    module_name=None,
                    source_file=str(source_path),
                    line_number=1,
                    missing_path=None,
                    diagnostic_message="unterminated string literal",
                    confidence=1.0,
                    reason="test",
                ),
                failure_reason="Corrective action execution failed.",
            )

            prompt = provider._build_prompt(request)

            self.assertIn("strongly prefer file_writes", prompt)
            self.assertIn("Avoid editor/inspection/validation commands", prompt)
            self.assertIn("---BEGIN_SOURCE_FILE---", prompt)


if __name__ == "__main__":
    unittest.main()
