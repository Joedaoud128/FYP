from __future__ import annotations

from phase4.domain.interfaces import ActionJournal
from phase4.domain.models import JournalRecord


class NoOpActionJournal(ActionJournal):
    def record(self, entry: JournalRecord) -> None:
        _ = entry
