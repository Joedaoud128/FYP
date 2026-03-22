from __future__ import annotations

import json
from pathlib import Path
import re
import shlex

from phase4.domain.models import LlmFallbackPlan, LlmFallbackRequest, LlmFallbackResponse, LlmFileWrite, LlmShellCommand
from phase4.runtime.ollama_client import OllamaClient


class LocalLlmProvider:
    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    def suggest_action(self, request: LlmFallbackRequest) -> LlmFallbackResponse:
        prompt = self._build_prompt(request)
        raw = self._client.chat(request.session_id, prompt)

        plan = self._parse_plan(raw)
        if plan is None:
            return LlmFallbackResponse(
                plan=None,
                raw_model_output=raw,
                accepted=False,
                rejection_reason="Model response did not contain a valid fallback plan.",
            )

        return LlmFallbackResponse(plan=plan, raw_model_output=raw, accepted=True)

    def _build_prompt(self, request: LlmFallbackRequest) -> str:
        prompt = (
            "You are a local code debugging assistant for fallback remediation. Return ONLY JSON. "
            "Schema: {\"commands\": [<command>], \"file_writes\": [{\"file_path\": \"...\", \"content\": \"...\"}], \"notes\": \"...\"}. "
            "Each command may be either a list of args or a single command string. "
            "You may return only commands, only file_writes, or both. "
            "\n\n"
            f"Failure reason: {request.failure_reason}\n"
            f"Exception: {request.error.exception_name}\n"
            f"Message: {request.error.message}\n"
            f"Module: {request.error.module_name}\n"
            f"Source file: {request.error.source_file}\n"
            f"Line: {request.error.line_number}\n"
            "Prefer minimal edits and commands needed to fix the failure."
        )

        if request.error.exception_name in {"SyntaxError", "IndentationError"}:
            prompt += (
                "\n\n"
                "For syntax-related failures, strongly prefer file_writes with corrected code content over shell commands. "
                "Avoid editor/inspection/validation commands (for example: notepad, code, vim, nano, py_compile). "
                "Return at least one file_write for the source file when possible."
            )

            source_content = self._read_source_file_content(request.error.source_file)
            if source_content is not None:
                prompt += (
                    "\n\n"
                    "Current source file content follows. If you produce a file_write for this file, provide corrected full file content."
                    "\n---BEGIN_SOURCE_FILE---\n"
                    f"{source_content}\n"
                    "---END_SOURCE_FILE---"
                )

        return prompt

    @staticmethod
    def _read_source_file_content(source_file: str | None) -> str | None:
        if not source_file:
            return None
        try:
            path = Path(source_file)
            if not path.exists() or not path.is_file():
                return None
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def _parse_plan(self, raw: str) -> LlmFallbackPlan | None:
        raw = raw.strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            candidate = self._extract_json_object(raw)
            if candidate is None:
                return None
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                return None

        commands_payload = payload.get("commands", [])
        if not commands_payload and "command" in payload:
            commands_payload = [payload.get("command")]
        file_writes_payload = payload.get("file_writes", [])
        notes = payload.get("notes")

        commands: list[LlmShellCommand] = []
        file_writes: list[LlmFileWrite] = []

        if isinstance(commands_payload, list):
            for item in commands_payload:
                if isinstance(item, list) and item:
                    commands.append(LlmShellCommand(command=[str(x) for x in item]))
                elif isinstance(item, str) and item.strip():
                    commands.append(LlmShellCommand(command=shlex.split(item, posix=False)))

        if isinstance(file_writes_payload, list):
            for item in file_writes_payload:
                if not isinstance(item, dict):
                    continue
                file_path = item.get("file_path")
                content = item.get("content")
                if isinstance(file_path, str) and isinstance(content, str):
                    file_writes.append(LlmFileWrite(file_path=file_path, content=content))

        if not commands and not file_writes:
            return None

        return LlmFallbackPlan(
            commands=commands,
            file_writes=file_writes,
            notes=str(notes) if isinstance(notes, str) else None,
        )

    @staticmethod
    def _extract_json_object(raw: str) -> str | None:
        fenced_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw, flags=re.IGNORECASE)
        if fenced_match:
            return fenced_match.group(1).strip()

        first_brace = raw.find("{")
        last_brace = raw.rfind("}")
        if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
            return None
        return raw[first_brace : last_brace + 1].strip()
