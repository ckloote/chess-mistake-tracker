"""Source name → implementation lookup. Register new sources here."""
from __future__ import annotations

from backend.app.sources.base import GameSource
from backend.app.sources.lichess_online import LichessOnlineSource
from backend.app.sources.lichess_study import LichessStudySource

_REGISTRY: dict[str, type[GameSource]] = {
    LichessOnlineSource.name: LichessOnlineSource,
    LichessStudySource.name: LichessStudySource,
}


def get_source(name: str) -> GameSource:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown game source: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]()


def known_sources() -> list[str]:
    return sorted(_REGISTRY)
