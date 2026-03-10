from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print

from seasonal_shift.models import FileOperation, ShowConfig, SonarrConfig, UndoEntry

from .cleanup import cleanup_shows
from .config import find_default_config, load_config
from .doctor import run_doctor
from .executor import execute_operations, find_latest_undo_file, get_default_undo_file
from .planner import detect_collisions, detect_duplicates, plan_operations
from .preview import show_preview
from .scanner import scan_show
from .sonarr import SonarrClient
from .undo import run_undo
from .watcher import run_watch

app = typer.Typer()


@app.command()
def run(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config", "-c", help="Config file (defaults to XDG config directory)"
        ),
    ] = None,
    undo_file: Annotated[
        Path | None,
        typer.Option(
            "--undo-file", help="Undo log file (defaults to XDG state directory)"
        ),
    ] = None,
) -> None:
    """
    Apply episode shifts defined in config.
    """

    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    all_operations: list[FileOperation] = []
    show_operations: list[tuple[ShowConfig, list[FileOperation]]] = []

    for show in cfg.shows:

        operations = plan_operations(show, scan_show)

        show_preview(show, operations)

        show_operations.append((show, operations))
        all_operations.extend(operations)

    collisions = detect_collisions(all_operations)

    if collisions:
        print("[red]Collision detected:[/]")
        for c in collisions:
            print(c)
        raise typer.Exit(1)

    duplicates = detect_duplicates(all_operations)

    if duplicates:
        print("[yellow]Duplicate destination detected:[/]")
        for a, b in duplicates:
            print(a, b)

    if not typer.confirm("Apply these changes?"):
        raise typer.Exit()

    if undo_file is None:
        undo_file = get_default_undo_file()

    execute_operations(all_operations, undo_file)

    removed = cleanup_shows(show.path for show in cfg.shows)

    if removed:
        print(f"[blue]Removed empty folders:[/] {len(removed)}")

    print(f"[green]Done.[/] Undo file saved to: {undo_file}")

    if cfg.sonarr:
        client = SonarrClient(str(cfg.sonarr.base_url), cfg.sonarr.api_key)
        _sonarr_update(client, cfg.sonarr, show_operations)


def _to_sonarr_path(path: Path, local_root: Path, sonarr_root: Path) -> Path:
    return sonarr_root / path.relative_to(local_root)


def _sonarr_update(
    client: SonarrClient,
    sonarr_cfg: SonarrConfig,
    show_operations: list[tuple[ShowConfig, list[FileOperation]]],
) -> None:
    for show, operations in show_operations:
        if not operations:
            continue

        try:
            series_id, _ = client.get_series(show.name)
        except Exception as e:
            print(f"[yellow]Sonarr: could not find series '{show.name}': {e}[/]")
            continue

        quality_id: int | None = None
        if show.sonarr_quality is not None:
            try:
                quality_id = client.get_quality_id(str(show.sonarr_quality))
            except Exception as e:
                print(
                    f"[yellow]Sonarr: could not resolve quality '{show.sonarr_quality}': {e}[/]"
                )

        refresh = client.refresh_series(series_id)
        client.wait_for_command(refresh["id"])

        for op in operations:
            try:
                sonarr_dest = (
                    _to_sonarr_path(
                        op.destination,
                        sonarr_cfg.local_shows_root,
                        sonarr_cfg.shows_root,
                    )
                    if sonarr_cfg.shows_root and sonarr_cfg.local_shows_root
                    else op.destination
                )
                ep_id = client.get_episode_id(series_id, op.season, op.episode)
                detect_kwargs = (
                    {"quality_id": quality_id} if quality_id is not None else {}
                )
                candidate = client.detect_file(
                    series_id, sonarr_dest, op.season, ep_id, **detect_kwargs
                )
                client.import_file(series_id, ep_id, candidate)
                print(
                    f"[green]Sonarr:[/] imported S{op.season:02d}E{op.episode:02d}"
                    f" → {op.destination.name}"
                )
            except Exception as e:
                print(
                    f"[yellow]Sonarr: failed S{op.season:02d}E{op.episode:02d}"
                    f" ({op.destination.name}): {e}[/]"
                )


@app.command()
def undo(
    undo_file: Annotated[
        Path | None,
        typer.Argument(help="Undo file (defaults to latest operation)"),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config", "-c", help="Config file (defaults to XDG config directory)"
        ),
    ] = None,
) -> None:
    """
    Undo the latest rename operation.
    """

    if undo_file is None:
        undo_file = find_latest_undo_file()

        if undo_file is None:
            print("[red]No undo files found.[/]")
            raise typer.Exit(1)

        print(f"[blue]Using latest undo file:[/] {undo_file}")

    run_undo(undo_file)

    print("[green]Undo complete[/]")

    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    if cfg.sonarr:
        client = SonarrClient(str(cfg.sonarr.base_url), cfg.sonarr.api_key)
        _sonarr_refresh_after_undo(client, undo_file, cfg.shows)


def _sonarr_refresh_after_undo(
    client: SonarrClient,
    undo_file: Path,
    cfg_shows: list[ShowConfig],
) -> None:
    import json

    entries = [UndoEntry.model_validate(e) for e in json.loads(undo_file.read_text())]

    affected: set[str] = set()
    for entry in entries:
        for show in cfg_shows:
            try:
                entry.destination.relative_to(show.path)
                affected.add(show.name)
                break
            except ValueError:
                pass

    for show_name in affected:
        try:
            series_id, _ = client.get_series(show_name)
            refresh = client.refresh_series(series_id)
            client.wait_for_command(refresh["id"])
            print(f"[green]Sonarr:[/] refreshed '{show_name}'")
        except Exception as e:
            print(f"[yellow]Sonarr: failed to refresh '{show_name}': {e}[/]")


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option(
            "--config", "-c", help="Config file (defaults to XDG config directory)"
        ),
    ] = None,
) -> None:
    """
    Run diagnostics on the library and configuration.
    """

    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    run_doctor(cfg.shows)


@app.command()
def watch(
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file (defaults to XDG config directory)"),
    ] = None,
) -> None:
    """
    Watch show directories and auto-apply episode shifts on new files.
    """
    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    sonarr_cb = None
    if cfg.sonarr:
        client = SonarrClient(str(cfg.sonarr.base_url), cfg.sonarr.api_key)
        sonarr_cfg = cfg.sonarr
        sonarr_cb = lambda show, ops: _sonarr_update(client, sonarr_cfg, [(show, ops)])  # noqa: E731

    run_watch(cfg, sonarr_cb)
