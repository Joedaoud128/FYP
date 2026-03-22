from __future__ import annotations

import json
import urllib.error
import urllib.request

from phase4.domain.interfaces import LlmRemediationProvider
from phase4.domain.models import ClassificationResult, ErrorRecord, ExecutionResult, LlmProposal
from phase4.llm.prompt_builder import build_llm_prompt
from phase4.llm.proposal_schema import parse_llm_proposal


class OllamaRemediationProvider(LlmRemediationProvider):
    def __init__(
        self,
        model: str = "qwen3.5:0.8b-instruct-q4_K_M",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 90,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def generate(
        self,
        command: list[str],
        execution_result: ExecutionResult,
        parsed_error: ErrorRecord | None,
        classification: ClassificationResult | None,
    ) -> LlmProposal | None:
        prompt = build_llm_prompt(command, execution_result, parsed_error, classification)
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        req = urllib.request.Request(
            url=f"{self._base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError):
            return None

        try:
            response_payload = json.loads(body)
        except json.JSONDecodeError:
            return None

        llm_text = response_payload.get("response", "")
        if not isinstance(llm_text, str):
            return None

        return parse_llm_proposal(llm_text)
