from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from .models import FileOperation, ShowConfig


def plan_operations(
    show: ShowConfig,
    scanner: Callable[[Path], Iterable[tuple[Path, re.Match[str]]]],
) -> list[FileOperation]:

    operations: list[FileOperation] = []

    for file, match in scanner(show.path):

        show_name, season, episode, ep_name_raw, ext = match.groups()

        season_int: int = int(season)
        episode_int: int = int(episode)

        if season_int not in show.seasons:
            continue

        config = show.seasons[season_int]

        if episode_int in config.episodes:
            mapping = config.episodes[episode_int]
            new_episode: int = mapping.episode
            if season_int == 0:
                new_season: int = 0
            elif mapping.season is not None:
                new_season = mapping.season
            else:
                new_season = season_int + config.season_offset
        else:
            new_season = season_int + config.season_offset
            new_episode = episode_int + config.episode_offset
            if new_episode < 1:
                continue

        episode_name: str | None = ep_name_raw.strip(" - ") if ep_name_raw else None

        if episode_name:
            new_name: str = (
                f"{show_name} - S{new_season:02d}E{new_episode:02d} - {episode_name}.{ext}"
            )
        else:
            new_name = f"{show_name} - S{new_season:02d}E{new_episode:02d}.{ext}"

        new_dir: Path = show.path / ("Specials" if new_season == 0 else f"Season {new_season}")
        new_path: Path = new_dir / new_name

        if new_path == file:
            continue

        operations.append(
            FileOperation(
                source=file,
                destination=new_path,
                season=season_int,
                episode=episode_int,
            )
        )

    return operations


def sort_operations(operations: list[FileOperation]) -> list[FileOperation]:
    n = len(operations)
    source_index: dict[Path, int] = {op.source: i for i, op in enumerate(operations)}
    in_degree = [0] * n
    dependents: list[list[int]] = [[] for _ in range(n)]

    for i, op in enumerate(operations):
        if op.destination in source_index:
            j = source_index[op.destination]  # j must run before i
            dependents[j].append(i)
            in_degree[i] += 1

    queue = [i for i in range(n) if in_degree[i] == 0]
    result: list[FileOperation] = []
    while queue:
        j = queue.pop()
        result.append(operations[j])
        for i in dependents[j]:
            in_degree[i] -= 1
            if in_degree[i] == 0:
                queue.append(i)

    if len(result) != n:
        raise ValueError("Circular mapping detected: operations form a cycle.")

    return result


def detect_collisions(operations: list[FileOperation]) -> list[Path]:
    # expects operations already sorted by sort_operations()
    freed: set[Path] = set()
    seen: set[Path] = set()
    collisions: list[Path] = []

    for op in operations:
        if op.destination in seen or (op.destination.exists() and op.destination not in freed):
            collisions.append(op.destination)
        freed.add(op.source)
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


def filter_processed(operations: list[FileOperation], processed: set[Path]) -> list[FileOperation]:
    return [op for op in operations if op.source not in processed]
