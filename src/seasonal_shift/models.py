from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, model_validator


class SonarrQuality(StrEnum):
    UNKNOWN = "Unknown"
    SDTV = "SDTV"
    DVD = "DVD"
    WEBDL_480P = "WEBDL-480p"
    HDTV_720P = "HDTV-720p"
    WEBDL_720P = "WEBDL-720p"
    BLURAY_720P = "Bluray-720p"
    WEBDL_1080P = "WEBDL-1080p"
    BLURAY_1080P = "Bluray-1080p"
    HDTV_1080P = "HDTV-1080p"
    RAW_HD = "Raw-HD"
    HDTV_2160P = "HDTV-2160p"
    WEBDL_2160P = "WEBDL-2160p"
    BLURAY_2160P = "Bluray-2160p"
    BLURAY_1080P_REMUX = "Bluray-1080p Remux"
    BLURAY_2160P_REMUX = "Bluray-2160p Remux"
    WEBRIP_480P = "WEBRip-480p"
    WEBRIP_720P = "WEBRip-720p"
    WEBRIP_1080P = "WEBRip-1080p"
    WEBRIP_2160P = "WEBRip-2160p"


class SonarrConfig(BaseModel):
    base_url: str
    api_key: str
    shows_root: Path | None = None
    local_shows_root: Path | None = None

    @model_validator(mode="after")
    def check_path_map_consistency(self) -> SonarrConfig:
        if (self.shows_root is None) != (self.local_shows_root is None):
            raise ValueError(
                "shows_root and local_shows_root must both be set or both omitted"
            )
        return self


class SeasonConfig(BaseModel):
    season_offset: int = 0
    episode_offset: int = 0


class ShowConfig(BaseModel):
    name: str
    path: Path
    seasons: dict[int, SeasonConfig]
    sonarr_quality: SonarrQuality | None = None


class Config(BaseModel):
    shows: list[ShowConfig]
    sonarr: SonarrConfig | None = None


class FileOperation(BaseModel):
    source: Path
    destination: Path
    season: int
    episode: int


class UndoEntry(BaseModel):
    source: Path
    destination: Path
