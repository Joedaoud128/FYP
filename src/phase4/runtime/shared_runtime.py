from __future__ import annotations

from threading import Lock

from phase4.runtime.ollama_client import OllamaClient
from phase4.runtime.session_manager import SessionManager


class SharedModelRuntime:
    _lock = Lock()
    _client: OllamaClient | None = None

    @classmethod
    def get_ollama_client(
        cls,
        base_url: str,
        model: str,
        timeout_seconds: int = 30,
        max_concurrent_requests: int = 1,
    ) -> OllamaClient:
        with cls._lock:
            if cls._client is None:
                cls._client = OllamaClient(
                    base_url=base_url,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    max_concurrent_requests=max_concurrent_requests,
                    session_manager=SessionManager(),
                )
            return cls._client
