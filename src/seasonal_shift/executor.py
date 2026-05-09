from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .models import FileOperation, StateEntry

APP_NAME: str = "seasonal-shift"


def get_state_dir() -> Path:
    xdg_state_home: str | None = os.getenv("XDG_STATE_HOME")

    if xdg_state_home:
        return Path(xdg_state_home) / APP_NAME

    return Path.home() / ".local" / "state" / APP_NAME


def get_state_file() -> Path:
    state_dir = get_state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "state.json"


def load_state(state_file: Path) -> list[StateEntry]:
    if not state_file.exists():
        return []
    return [StateEntry.model_validate(e) for e in json.loads(state_file.read_text())]  # pyright: ignore[reportAny]


def write_state(state_file: Path, entries: list[StateEntry]) -> None:
    if entries:
        state_file.write_text(
            "[\n" + ",\n".join(e.model_dump_json(indent=2) for e in entries) + "\n]"
        )
    else:
        state_file.write_text("[]")


def load_processed(state_file: Path) -> set[Path]:
    return {entry.current for entry in load_state(state_file)}


def find_latest_undo_file_legacy() -> Path | None:
    state_dir = get_state_dir()

    if not state_dir.exists():
        return None

    undo_files = sorted(
        state_dir.glob("undo-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    return undo_files[0] if undo_files else None


def execute_operations(
    operations: list[FileOperation],
    state_file: Path,
    run_id: str | None = None,
) -> None:
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S%f")
    existing = load_state(state_file)
    new_entries: list[StateEntry] = []

    for op in operations:
        op.destination.parent.mkdir(parents=True, exist_ok=True)
        op.source.rename(op.destination)
        new_entries.append(StateEntry(original=op.source, current=op.destination, run_id=run_id))

    write_state(state_file, existing + new_entries)
