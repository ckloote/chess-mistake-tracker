"""Source name → implementation lookup. Register new sources here.

Each entry is a factory taking the AppSettings singleton, so runtime-tunable
knobs (study IDs, player aliases — edited via PATCH /settings) come from the
DB row at import time rather than the boot-time env. Sources that need no
settings just ignore the argument.
"""
from __future__ import annotations

from collections.abc import Callable

from backend.app.models import AppSettings
from backend.app.sources.base import GameSource
from backend.app.sources.chesscom import ChessComSource
from backend.app.sources.lichess_online import LichessOnlineSource
from backend.app.sources.lichess_study import LichessStudySource

_REGISTRY: dict[str, Callable[[AppSettings], GameSource]] = {
    LichessOnlineSource.name: lambda _settings: LichessOnlineSource(),
    ChessComSource.name: lambda _settings: ChessComSource(),
    LichessStudySource.name: lambda settings: LichessStudySource(
        study_ids=list(settings.lichess_study_ids),
        aliases=list(settings.study_player_aliases),
    ),
}


def get_source(name: str, app_settings: AppSettings) -> GameSource:
    """Build the named source from the current AppSettings. Raises KeyError
    for an unknown name; may raise ValueError if stored settings are invalid
    for the source (e.g. a malformed study id that predates PATCH-time
    validation)."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown game source: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name](app_settings)


def known_sources() -> list[str]:
    return sorted(_REGISTRY)
