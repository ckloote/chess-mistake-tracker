"""chess.com game source.

Walks the published monthly archives (`GET /pub/player/{u}/games/archives`,
then one GET per month) newest-first and yields each standard-rules game as a
GameRecord. The pure JSON→record functions are exposed at module scope so they
can be unit-tested without any network access.

chess.com etiquette (verified against api.chess.com):
- Requests from one IP must be **serial** — parallel fetches get 429. The
  fetch loop below is strictly sequential.
- Send a descriptive User-Agent so they can contact the operator.

chess.com PGNs never carry `%eval` annotations, so records always come back
`has_evals=false` and are analyzed via the local-Stockfish path (F3). `%clk`
comments (with fractional seconds) are present and parse through the existing
PGN analyzer unchanged.
"""
from __future__ import annotations

import io
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import chess.pgn
import httpx

from backend.app.models import User
from backend.app.sources.base import GameRecord, RefreshUnsupported, SourceMisconfigured
from backend.app.sources.pgn_headers import parse_played_at

CHESSCOM_API_BASE = "https://api.chess.com"

# Descriptive UA per chess.com's published API etiquette.
USER_AGENT = "chess-mistake-tracker (personal analysis tool)"


def extract_game_id(url: str | None) -> str | None:
    """`https://www.chess.com/game/daily/747757185` → `"daily/747757185"`.
    Keeping the `live|daily` segment lets the frontend rebuild the web URL as
    `https://www.chess.com/game/{source_game_id}`."""
    if not url:
        return None
    marker = "/game/"
    idx = url.find(marker)
    if idx == -1:
        return None
    tail = url[idx + len(marker):].strip("/")
    return tail or None


def record_from_archive_game(game_json: dict, chesscom_username: str) -> GameRecord | None:
    """Build a GameRecord from one entry of a monthly-archive `games` array.
    Returns None (caller skips) for variants (`rules != "chess"` — custom-FEN
    starts are fine, but 960/crazyhouse would break analysis assumptions),
    when the configured user is neither player, or when `pgn`/`url` is
    missing."""
    if game_json.get("rules") != "chess":
        return None
    pgn_text = game_json.get("pgn")
    source_game_id = extract_game_id(game_json.get("url"))
    if not pgn_text or not source_game_id:
        return None

    white = (game_json.get("white") or {}).get("username", "")
    black = (game_json.get("black") or {}).get("username", "")
    username_lc = chesscom_username.lower()
    if white.lower() == username_lc:
        user_color = "white"
    elif black.lower() == username_lc:
        user_color = "black"
    else:
        return None

    headers = chess.pgn.read_headers(io.StringIO(pgn_text)) or chess.pgn.Headers()
    played_at = parse_played_at(headers)
    if played_at is None and game_json.get("end_time"):
        played_at = datetime.fromtimestamp(game_json["end_time"], tz=timezone.utc)

    return GameRecord(
        source="chesscom",
        source_game_id=source_game_id,
        pgn=pgn_text if pgn_text.endswith("\n") else pgn_text + "\n",
        user_color=user_color,
        white=white,
        black=black,
        result=headers.get("Result", "*"),
        # Always false in practice — chess.com PGNs carry no engine evals —
        # but keep the honest check rather than hardcoding.
        has_evals="[%eval " in pgn_text,
        white_elo=(game_json.get("white") or {}).get("rating"),
        black_elo=(game_json.get("black") or {}).get("rating"),
        time_control=game_json.get("time_control") or None,
        played_at=played_at,
    )


class ChessComSource:
    name = "chesscom"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[GameRecord]:
        if not user.chesscom_username:
            raise SourceMisconfigured(
                "No chess.com username configured. Set it on the Settings page."
            )
        username = user.chesscom_username
        if since is not None and since.tzinfo is None:
            # A naive datetime is taken as UTC — same convention as the
            # Lichess source (.timestamp() alone would use the server zone).
            since = since.replace(tzinfo=timezone.utc)

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        try:
            archives = await self._get_json(
                client, f"{CHESSCOM_API_BASE}/pub/player/{username}/games/archives"
            )
            yielded = 0
            # Archive list is chronological; walk months newest-first so a
            # `limit` covers the most recent games.
            for month_url in reversed(archives.get("archives", [])):
                month = await self._get_json(client, month_url)
                games = sorted(
                    month.get("games", []),
                    key=lambda g: g.get("end_time", 0),
                    reverse=True,
                )
                for game_json in games:
                    if since is not None and game_json.get("end_time"):
                        ended = datetime.fromtimestamp(
                            game_json["end_time"], tz=timezone.utc
                        )
                        if ended < since:
                            # Games are sorted newest-first, so everything
                            # from here back is older than `since`.
                            return
                    record = record_from_archive_game(game_json, username)
                    if record is None:
                        continue
                    yield record
                    yielded += 1
                    if limit is not None and yielded >= limit:
                        return
        finally:
            if owns_client:
                await client.aclose()

    async def fetch_game_by_id(self, user: User, game_id: str) -> GameRecord | None:
        raise RefreshUnsupported(
            "chess.com games don't change after they finish (and there is no "
            "request-analysis flow), so refresh has no purpose. Re-import to "
            "pick up new games."
        )

    @staticmethod
    async def _get_json(client: httpx.AsyncClient, url: str) -> dict:
        response = await client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json()
