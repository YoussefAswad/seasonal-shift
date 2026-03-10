from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from rich import print

from .models import FileOperation, ShowConfig


EP_PATTERN = re.compile(r"S(\d{2})E(\d{2})")


def _extract_episode(path: Path) -> Tuple[int, int]:
    match = EP_PATTERN.search(path.name)

    if not match:
        return (0, 0)

    return int(match.group(1)), int(match.group(2))


def show_preview(show: ShowConfig, operations: List[FileOperation]) -> None:
    """
    Display preview grouped by season showing filename changes.
    """

    if not operations:
        print(f"[yellow]{show.name}: no changes[/]")
        return

    grouped: Dict[Tuple[int, int], List[FileOperation]] = defaultdict(list)

    for op in operations:
        old_s, _ = _extract_episode(op.source)
        new_s, _ = _extract_episode(op.destination)

        grouped[(old_s, new_s)].append(op)

    print()
    print(f"[bold]{show.name}[/]")
    print("-" * len(show.name))
    print()

    for (old_s, new_s), ops in sorted(grouped.items()):

        if old_s == new_s:
            print(f"[cyan]Season {old_s}[/]")
        else:
            print(f"[cyan]Season {old_s} → {new_s}[/]")

        for op in sorted(ops, key=lambda o: o.source.name):

            old_name = op.source.name
            new_name = op.destination.name

            if old_name == new_name:
                print(f"  {old_name}")
            else:
                print(f"  {old_name}")
                print(f"    → {new_name}")

        print()
