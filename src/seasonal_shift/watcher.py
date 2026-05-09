from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from rich import print
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import load_config
from .cleanup import remove_empty_dirs
from .executor import execute_operations, get_state_file, load_processed
from .models import Config, FileOperation, ShowConfig
from .planner import filter_processed, plan_operations, sort_operations
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
        self._in_flight: set[Path] = set()
        self._lock = threading.Lock()

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._handle(Path(event.dest_path))

    def _handle(self, path: Path) -> None:
        with self._lock:
            if path in self._in_flight:
                self._in_flight.discard(path)
                return

        operations = plan_operations(self._show, lambda _: _scan_single(path))
        if not operations:
            return

        try:
            operations = sort_operations(operations)
        except ValueError as e:
            print(f"[yellow]Watch:[/] skipping — {e}")
            return

        with self._lock:
            for op in operations:
                self._in_flight.add(op.destination)

        state_file = get_state_file()
        processed = load_processed(state_file)
        filtered = filter_processed(operations, processed)
        if not filtered:
            with self._lock:
                for op in operations:
                    self._in_flight.discard(op.destination)
            return
        operations = filtered

        execute_operations(operations, state_file)
        for op in operations:
            print(f"[green]Watch:[/] {op.source.name} → {op.destination.name}")
        remove_empty_dirs(self._show.path)
        if self._sonarr_cb:
            self._sonarr_cb(self._show, operations)


class _ConfigReloadHandler(FileSystemEventHandler):
    def __init__(self, config_path: Path, event: threading.Event) -> None:
        self._config_path = config_path
        self._event = event

    def _notify_if_config(self, src_path: str, is_directory: bool) -> None:
        if not is_directory and Path(src_path) == self._config_path:
            self._event.set()

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        self._notify_if_config(event.src_path, event.is_directory)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        self._notify_if_config(event.src_path, event.is_directory)


def run_watch(
    config_path: Path,
    sonarr_cb_factory: Callable[[Config], Callable[[ShowConfig, list[FileOperation]], Any] | None],
) -> None:
    while True:
        try:
            cfg = load_config(config_path)
        except Exception as e:
            print(f"[red]Config error: {e}[/]")
            return

        reload_event = threading.Event()
        observer = Observer()

        sonarr_cb = sonarr_cb_factory(cfg)
        scheduled = 0
        for show in cfg.shows:
            if not show.path.exists():
                print(f"[yellow]Watch:[/] skipping [bold]{show.name}[/] — path not found: {show.path}")
                continue
            handler = EpisodeEventHandler(show, sonarr_cb)
            observer.schedule(handler, str(show.path), recursive=True)
            scheduled += 1

        config_handler = _ConfigReloadHandler(config_path, reload_event)
        observer.schedule(config_handler, str(config_path.parent), recursive=False)

        observer.start()
        print(f"[blue]Watching {scheduled} show(s). Press Ctrl+C to stop.[/]")
        try:
            while not reload_event.wait(0.5):
                pass
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            return

        observer.stop()
        observer.join()
        print("[blue]Config changed, reloading…[/]")
