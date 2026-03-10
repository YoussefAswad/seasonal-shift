from __future__ import annotations

from pathlib import Path
from typing import Any, NotRequired, Required, TypedDict

import requests


class Series(TypedDict):
    id: int
    title: str
    path: str


class Episode(TypedDict):
    id: int
    episodeNumber: int


class Language(TypedDict):
    id: int
    name: str


class QualityWrapper(TypedDict):
    quality: dict[str, Any]


class ManualImportCandidate(TypedDict):
    # fields Sonarr always returns
    path: Required[str]
    quality: Required[QualityWrapper]

    # fields we set manually
    seriesId: NotRequired[int]
    seasonNumber: NotRequired[int]
    episodeIds: NotRequired[list[int]]
    languages: NotRequired[list[Language]]


class SonarrClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.session: requests.Session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    def _get(  # pyright: ignore[reportAny]
        self,
        endpoint: str,
        **kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]
    ) -> Any:  # pyright: ignore[reportExplicitAny]
        r = self.session.get(
            f"{self.base_url}{endpoint}", **kwargs  # pyright: ignore[reportAny]
        )
        r.raise_for_status()
        return r.json()  # pyright: ignore[reportAny]

    def _post(  # pyright: ignore[reportAny]
        self,
        endpoint: str,
        **kwargs: Any,  # pyright: ignore[reportExplicitAny, reportAny]
    ) -> Any:  # pyright: ignore[reportExplicitAny]
        r = self.session.post(
            f"{self.base_url}{endpoint}", **kwargs  # pyright: ignore[reportAny]
        )
        r.raise_for_status()
        return r.json()  # pyright: ignore[reportAny]

    # ------------------------------------------------------------
    # Series
    # ------------------------------------------------------------

    def get_series(self, show_name: str) -> tuple[int, str]:
        series_list: list[Series] = self._get(  # pyright: ignore[reportAny]
            "/api/v3/series"
        )

        for series in series_list:
            if series["title"].lower() == show_name.lower():
                return series["id"], series["path"]

        raise RuntimeError(f"Series not found: {show_name}")

    # ------------------------------------------------------------
    # Episodes
    # ------------------------------------------------------------

    def get_episode_id(self, series_id: int, season: int, episode: int) -> int:
        episodes: list[Episode] = self._get(  # pyright: ignore[reportAny]
            "/api/v3/episode",
            params={
                "seriesId": series_id,
                "seasonNumber": season,
            },
        )

        for ep in episodes:
            if ep["episodeNumber"] == episode:
                return ep["id"]

        raise RuntimeError(f"Episode not found S{season:02}E{episode:02}")

    # ------------------------------------------------------------
    # Manual Import
    # ------------------------------------------------------------

    def detect_file(
        self,
        series_id: int,
        file_path: str | Path,
        season: int,
        episode_id: int,
        *,
        quality_id: int = 17,
    ) -> ManualImportCandidate:

        path = Path(file_path)
        folder = str(path.parent)

        candidates: list[ManualImportCandidate] = (  # pyright: ignore[reportAny]
            self._get(
                "/api/v3/manualimport",
                params={
                    "folder": folder,
                    "seriesId": series_id,
                },
            )
        )

        if not candidates:
            raise RuntimeError("Sonarr detected no files")

        candidate = next(
            (c for c in candidates if c["path"] == str(path)),
            None,
        )

        if candidate is None:
            raise RuntimeError(f"File not detected by Sonarr: {path}")

        candidate["seriesId"] = series_id
        candidate["seasonNumber"] = season
        candidate["episodeIds"] = [episode_id]

        candidate["quality"]["quality"]["id"] = quality_id

        # candidate["languages"] = [
        #     {
        #         "id": 8,
        #         "name": "Japanese",
        #     }
        # ]

        result: list[ManualImportCandidate] = self._post(  # pyright: ignore[reportAny]
            "/api/v3/manualimport",
            json=[candidate],
        )

        return result[0]

    def import_file(
        self,
        series_id: int,
        episode_id: int,
        candidate: ManualImportCandidate,
    ) -> dict[str, Any]:

        candidate["seriesId"] = series_id
        candidate["episodeIds"] = [episode_id]

        payload: dict[str, Any] = {
            "name": "ManualImport",
            "files": [candidate],
            "importMode": "auto",
        }

        return self._post("/api/v3/command", json=payload)

    def refresh_series(self, series_id: int) -> dict[str, Any]:
        payload = {
            "name": "RefreshSeries",
            "seriesId": series_id,
        }

        return self._post("/api/v3/command", json=payload)
