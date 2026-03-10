from __future__ import annotations

from pathlib import Path
from typing import Callable

from .models import FileOperation, ShowConfig


def plan_operations(
    show: ShowConfig,
    scanner: Callable[[Path], tuple[Path, object]],
) -> list[FileOperation]:

    operations: list[FileOperation] = []

    for file, match in scanner(show.path):

        show_name, season, episode, ep_name_raw, ext = match.groups()

        season_int: int = int(season)
        episode_int: int = int(episode)

        if season_int not in show.seasons:
            continue

        config = show.seasons[season_int]

        new_season: int = season_int + config.season_offset
        new_episode: int = episode_int + config.episode_offset

        if new_episode < 1:
            continue

        episode_name: str | None = (
            ep_name_raw.strip(" - ") if ep_name_raw else None
        )

        if episode_name:
            new_name: str = (
                f"{show_name} - S{new_season:02d}E{new_episode:02d} - {episode_name}.{ext}"
            )
        else:
            new_name = f"{show_name} - S{new_season:02d}E{new_episode:02d}.{ext}"

        new_dir: Path = show.path / f"Season {new_season}"
        new_path: Path = new_dir / new_name

        operations.append(
            FileOperation(
                source=file,
                destination=new_path,
            )
        )

    return operations


def detect_collisions(operations: list[FileOperation]) -> list[Path]:

    seen: set[Path] = set()
    collisions: list[Path] = []

    for op in operations:

        if op.destination in seen or op.destination.exists():
            collisions.append(op.destination)

        seen.add(op.destination)

    return collisions


def detect_duplicates(operations: list[FileOperation]) -> list[tuple[Path, Path]]:

    seen: dict[Path, Path] = {}
    duplicates: list[tuple[Path, Path]] = []

    for op in operations:

        if op.destination in seen:
            duplicates.append((seen[op.destination], op.source))
        else:
            seen[op.destination] = op.source

    return duplicates
