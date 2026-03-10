from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from rich import print
from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .cleanup import remove_empty_dirs
from .executor import execute_operations, get_default_undo_file
from .models import Config, FileOperation, ShowConfig
from .planner import plan_operations
from .scanner import EPISODE_PATTERN


def _scan_single(file: Path) -> Iterator[tuple[Path, re.Match[str]]]:
    match = EPISODE_PATTERN.match(file.name)
    if match:
        yield file, match


class EpisodeEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        show: ShowConfig,
        sonarr_cb: Callable[[ShowConfig, list[FileOperation]], Any] | None,
    ) -> None:
        self._show = show
        self._sonarr_cb = sonarr_cb

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(Path(event.dest_path))

    def _handle(self, path: Path) -> None:
        operations = plan_operations(self._show, lambda _: _scan_single(path))
        if not operations:
            return
        undo_file = get_default_undo_file()
        execute_operations(operations, undo_file)
        for op in operations:
            print(f"[green]Watch:[/] {op.source.name} → {op.destination.name}")
        remove_empty_dirs(self._show.path)
        if self._sonarr_cb:
            self._sonarr_cb(self._show, operations)


def run_watch(
    cfg: Config,
    sonarr_cb: Callable[[ShowConfig, list[FileOperation]], Any] | None = None,
) -> None:
    observer = Observer()
    for show in cfg.shows:
        handler = EpisodeEventHandler(show, sonarr_cb)
        observer.schedule(handler, str(show.path), recursive=True)

    observer.start()
    print(f"[blue]Watching {len(cfg.shows)} show(s). Press Ctrl+C to stop.[/]")
    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
