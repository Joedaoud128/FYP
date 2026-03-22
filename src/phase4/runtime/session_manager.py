from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List


PHASE4_SESSION_ID = "phase4_debug_session"


@dataclass
class SessionManager:
    _histories: Dict[str, List[dict[str, str]]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def add_user_message(self, session_id: str, message: str) -> None:
        with self._lock:
            history = self._histories.setdefault(session_id, [])
            history.append({"role": "user", "content": message})

    def add_assistant_message(self, session_id: str, message: str) -> None:
        with self._lock:
            history = self._histories.setdefault(session_id, [])
            history.append({"role": "assistant", "content": message})

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            history = self._histories.get(session_id, [])
            return list(history)
