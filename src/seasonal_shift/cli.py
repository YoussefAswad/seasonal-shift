from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import print

from seasonal_shift.models import FileOperation

from .cleanup import cleanup_shows
from .config import find_default_config, load_config
from .doctor import run_doctor
from .executor import execute_operations, find_latest_undo_file, get_default_undo_file
from .planner import detect_collisions, detect_duplicates, plan_operations
from .preview import show_preview
from .scanner import scan_show
from .undo import run_undo

app = typer.Typer()


@app.command()
def run(
    config: Annotated[
        Path | None,
        typer.Option(
            None,
            "--config",
            "-c",
            help="Config file (defaults to XDG config directory)",
        ),
    ],
    undo_file: Annotated[
        Path | None,
        typer.Option(
            None,
            "--undo-file",
            help="Undo log file (defaults to XDG state directory)",
        ),
    ],
) -> None:
    """
    Apply episode shifts defined in config.
    """

    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    all_operations: list[FileOperation] = []

    for show in cfg.shows:

        operations = plan_operations(show, scan_show)

        show_preview(show, operations)

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


@app.command()
def undo(
    undo_file: Annotated[
        Path | None,
        typer.Argument(
            None,
            help="Undo file (defaults to latest operation)",
        ),
    ],
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


@app.command()
def doctor(
    config: Annotated[
        Path | None,
        typer.Option(
            None,
            "--config",
            "-c",
            help="Config file (defaults to XDG config directory)",
        ),
    ],
) -> None:
    """
    Run diagnostics on the library and configuration.
    """

    if config is None:
        config = find_default_config()

    cfg = load_config(config)

    run_doctor(cfg.shows)
