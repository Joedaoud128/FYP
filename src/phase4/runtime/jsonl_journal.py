from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from phase4.domain.interfaces import ActionJournal
from phase4.domain.models import JournalRecord


class JsonlActionJournal(ActionJournal):
    def __init__(self, file_path: str) -> None:
        self._file_path = file_path

    def record(self, entry: JournalRecord) -> None:
        path = Path(self._file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
