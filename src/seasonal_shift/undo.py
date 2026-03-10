from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import UndoEntry


def run_undo(undo_file: Path) -> None:

    data = json.loads(undo_file.read_text())

    entries: List[UndoEntry] = [
        UndoEntry.model_validate(e) for e in data
    ]

    # reverse order for safety
    for entry in reversed(entries):

        if not entry.source.exists():
            continue

        # recreate directory if cleanup removed it
        entry.destination.parent.mkdir(parents=True, exist_ok=True)

        entry.source.rename(entry.destination)
