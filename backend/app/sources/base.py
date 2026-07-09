from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from backend.app.models import User


class SourceMisconfigured(Exception):
    """Per-user configuration required by a source is missing or invalid
    (e.g. no chess.com username on the User row). The API maps this to a 400
    telling the user what to set."""


class RefreshUnsupported(Exception):
    """The source has no meaningful per-game refresh (e.g. finished chess.com
    games are immutable and there is no request-analysis flow). The API maps
    this to a 400."""


@dataclass(frozen=True, slots=True)
class GameRecord:
    """A single ingested game in canonical form. PGN is the source of truth;
    the other fields are convenience caches parsed from headers."""

    source: str
    source_game_id: str
    pgn: str

    user_color: str  # "white" | "black"
    white: str
    black: str
    result: str  # "1-0" | "0-1" | "1/2-1/2" | "*"
    has_evals: bool

    white_elo: int | None = None
    black_elo: int | None = None
    time_control: str | None = None
    played_at: datetime | None = None


@runtime_checkable
class GameSource(Protocol):
    """Pluggable game source. Implementations are responsible for translating
    their backend's representation into PGN-anchored GameRecords."""

    name: str

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[GameRecord]: ...

    async def fetch_game_by_id(self, user: User, game_id: str) -> GameRecord | None:
        """Re-fetch one game by its source_game_id (the refresh workflow).
        `user` is needed to resolve user_color — DESIGN.md's original
        `(game_id)`-only signature couldn't build a GameRecord. Returns None
        when the fetched data no longer lists the user as a player; raises
        httpx errors for network / upstream failures (the caller maps them
        to HTTP responses). Sources where finished games are immutable may
        raise RefreshUnsupported instead."""
        ...
