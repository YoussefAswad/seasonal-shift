from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic.networks import UrlConstraints


class SonarrConfig(BaseModel):
    base_url: UrlConstraints
    api_key: str


class SeasonConfig(BaseModel):
    season_offset: int = 0
    episode_offset: int = 0


class ShowConfig(BaseModel):
    name: str
    path: Path
    seasons: dict[int, SeasonConfig]


class Config(BaseModel):
    shows: list[ShowConfig]
    sonarr: SonarrConfig | None = None


class FileOperation(BaseModel):
    source: Path
    destination: Path


class UndoEntry(BaseModel):
    source: Path
    destination: Path
