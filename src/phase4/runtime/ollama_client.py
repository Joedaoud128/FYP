from __future__ import annotations

import json
import time
from threading import BoundedSemaphore
from urllib import request
from urllib.error import URLError

from phase4.runtime.session_manager import SessionManager


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 30,
        max_concurrent_requests: int = 1,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.5,
        session_manager: SessionManager | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._semaphore = BoundedSemaphore(value=max_concurrent_requests)
        self._session_manager = session_manager or SessionManager()

    def health_check(self) -> bool:
        payload = json.dumps({"model": self._model, "prompt": "ping", "stream": False}).encode("utf-8")
        req = request.Request(
            url=f"{self._base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._timeout_seconds):
                return True
        except URLError:
            return False

    def chat(self, session_id: str, user_message: str) -> str:
        self._session_manager.add_user_message(session_id, user_message)
        messages = self._session_manager.get_messages(session_id)

        with self._semaphore:
            for attempt in range(1, self._max_retries + 1):
                try:
                    response_text = self._chat_once(messages)
                    self._session_manager.add_assistant_message(session_id, response_text)
                    return response_text
                except URLError:
                    if attempt == self._max_retries:
                        raise
                    time.sleep(self._retry_backoff_seconds * attempt)

        return ""

    def _chat_once(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps(
            {
                "model": self._model,
                "messages": messages,
                "stream": False,
                "keep_alive": "10m",
            }
        ).encode("utf-8")
        req = request.Request(
            url=f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self._timeout_seconds) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            message = payload.get("message", {})
            return str(message.get("content", ""))
