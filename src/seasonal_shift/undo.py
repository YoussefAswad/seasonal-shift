from __future__ import annotations

import json
from pathlib import Path

from .executor import find_latest_undo_file_legacy, load_state, write_state
from .models import StateEntry, UndoEntry


def _run_undo_legacy(undo_file: Path) -> list[StateEntry]:
    data = json.loads(undo_file.read_text())  # pyright: ignore[reportAny]
    entries = [UndoEntry.model_validate(e) for e in data]  # pyright: ignore[reportAny]

    undone: list[StateEntry] = []
    for entry in reversed(entries):
        if not entry.source.exists():
            continue
        entry.destination.parent.mkdir(parents=True, exist_ok=True)
        entry.source.rename(entry.destination)
        undone.append(StateEntry(original=entry.destination, current=entry.source, run_id="legacy"))

    return undone


def run_undo(state_file: Path) -> list[StateEntry]:
    entries = load_state(state_file)

    if not entries:
        legacy = find_latest_undo_file_legacy()
        if legacy:
            return _run_undo_legacy(legacy)
        return []

    latest_run_id = max(e.run_id for e in entries)
    batch = [e for e in entries if e.run_id == latest_run_id]
    remaining = [e for e in entries if e.run_id != latest_run_id]

    undone: list[StateEntry] = []
    for entry in reversed(batch):
        if not entry.current.exists():
            continue
        entry.original.parent.mkdir(parents=True, exist_ok=True)
        entry.current.rename(entry.original)
        undone.append(entry)

    write_state(state_file, remaining)
    return undone
