"""Lichess online game source.

Hits `GET /api/games/user/{username}` and yields each game as a GameRecord.
The pure-PGN parsing functions are exposed at module scope so they can be
unit-tested without any network access.
"""
from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from urllib.parse import urlsplit

import chess.pgn
import httpx

from backend.app.models import User
from backend.app.sources.base import GameRecord

LICHESS_API_BASE = "https://lichess.org"


def _parse_int(value: str | None) -> int | None:
    if not value or value == "?":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_played_at(headers: chess.pgn.Headers) -> datetime | None:
    date = headers.get("UTCDate") or headers.get("Date")
    time = headers.get("UTCTime")
    if not date or date == "????.??.??":
        return None
    try:
        if time:
            return datetime.strptime(f"{date} {time}", "%Y.%m.%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        return datetime.strptime(date, "%Y.%m.%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _extract_lichess_game_id(site_url: str) -> str:
    """`https://lichess.org/abc12345` → `abc12345`. Take the first path
    component to be safe against `/black` / `/white` suffixes."""
    path = urlsplit(site_url).path.strip("/")
    return path.split("/", 1)[0] if path else site_url


def _record_from_game(game: chess.pgn.Game, lichess_username: str) -> GameRecord | None:
    """Build a GameRecord from a parsed python-chess Game. Returns None if the
    configured user isn't one of the players (caller should skip)."""
    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")
    source_game_id = _extract_lichess_game_id(headers.get("Site", ""))
    if not source_game_id:
        return None

    username_lc = lichess_username.lower()
    if white.lower() == username_lc:
        user_color = "white"
    elif black.lower() == username_lc:
        user_color = "black"
    else:
        return None

    pgn_text = str(game) + "\n"
    return GameRecord(
        source="lichess_online",
        source_game_id=source_game_id,
        pgn=pgn_text,
        user_color=user_color,
        white=white,
        black=black,
        result=headers.get("Result", "*"),
        has_evals="[%eval " in pgn_text,
        white_elo=_parse_int(headers.get("WhiteElo")),
        black_elo=_parse_int(headers.get("BlackElo")),
        time_control=headers.get("TimeControl") or None,
        played_at=_parse_played_at(headers),
    )


def parse_pgn_game(pgn_text: str, lichess_username: str) -> GameRecord | None:
    """Parse a single PGN game text into a GameRecord, or None on miss."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return None
    return _record_from_game(game, lichess_username)


def parse_pgn_stream(text: str, lichess_username: str) -> list[GameRecord]:
    """Parse multi-game PGN text into a list of GameRecords. Games where the
    configured user isn't a player are silently skipped."""
    stream = io.StringIO(text)
    records: list[GameRecord] = []
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        record = _record_from_game(game, lichess_username)
        if record is not None:
            records.append(record)
    return records


class LichessOnlineSource:
    name = "lichess_online"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[GameRecord]:
        params: dict[str, str | int] = {"evals": "true", "clocks": "true", "pgnInJson": "false"}
        if limit is not None:
            params["max"] = limit
        if since is not None:
            # A naive datetime is taken as UTC — .timestamp() alone would
            # interpret it in the server's local zone.
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            params["since"] = int(since.timestamp() * 1000)

        url = f"{LICHESS_API_BASE}/api/games/user/{user.lichess_username}"
        for record in await self._fetch(url, params, user.lichess_username):
            yield record

    async def fetch_game_by_id(self, user: User, game_id: str) -> GameRecord | None:
        """Re-fetch one game via `GET /game/export/{id}` — the refresh
        workflow, which picks up evals once Lichess analysis has been
        requested for the game. Returns None if the user is no longer a
        player in the returned PGN; raises httpx.HTTPStatusError on 404 /
        upstream errors."""
        url = f"{LICHESS_API_BASE}/game/export/{game_id}"
        params: dict[str, str | int] = {"evals": "true", "clocks": "true"}
        records = await self._fetch(url, params, user.lichess_username)
        return records[0] if records else None

    async def _fetch(
        self,
        url: str,
        params: dict[str, str | int],
        lichess_username: str,
    ) -> list[GameRecord]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        try:
            response = await client.get(
                url,
                params=params,
                headers={"Accept": "application/x-chess-pgn"},
            )
            response.raise_for_status()
            text = response.text
        finally:
            if owns_client:
                await client.aclose()

        return parse_pgn_stream(text, lichess_username)
