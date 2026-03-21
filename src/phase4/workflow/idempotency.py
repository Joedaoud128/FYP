from __future__ import annotations

from phase4.domain.interfaces import IdempotencyPolicy


class InMemoryIdempotencyPolicy(IdempotencyPolicy):
    def __init__(self) -> None:
        self._seen_pairs: set[tuple[str, str]] = set()

    def should_block(self, error_fingerprint: str, action_fingerprint: str) -> bool:
        return (error_fingerprint, action_fingerprint) in self._seen_pairs

    def remember(self, error_fingerprint: str, action_fingerprint: str) -> None:
        self._seen_pairs.add((error_fingerprint, action_fingerprint))
