"""Lichess study game source.

A Lichess study is a folder of chapters (each chapter is a game / annotated
position). For each configured study ID, we fetch the multi-game PGN, parse
each chapter as a python-chess Game, and emit one GameRecord per chapter
where the configured user is White or Black.

Chapters where the user isn't a player (e.g. analysis of a pro game) are
silently skipped — that's the MVP behavior in DESIGN.md §"Open Questions".
"""
from __future__ import annotations

import io
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from urllib.parse import urlsplit

import chess.pgn
import httpx

from backend.app.config import get_settings
from backend.app.models import User
from backend.app.sources.base import GameRecord
from backend.app.sources.lichess_online import (
    _parse_int,
    _parse_played_at,
)

LICHESS_API_BASE = "https://lichess.org"
log = logging.getLogger(__name__)


def _extract_chapter_id(site_url: str, study_id: str) -> str | None:
    """`https://lichess.org/study/{studyId}/{chapterId}` → `{chapterId}`.
    Returns None if the URL doesn't reference this study."""
    path = urlsplit(site_url).path.strip("/")
    parts = path.split("/")
    # Expect ["study", studyId, chapterId, ...]
    if len(parts) >= 3 and parts[0] == "study" and parts[1] == study_id:
        return parts[2]
    return None


def _resolve_user_color(
    white: str, black: str, lichess_username: str, aliases: list[str]
) -> str | None:
    """Decide whether the configured user is white, black, or absent in this
    chapter. Matches case-insensitively against the username and any alias."""
    candidates = {n.lower() for n in (lichess_username, *aliases) if n}
    if white.lower() in candidates:
        return "white"
    if black.lower() in candidates:
        return "black"
    return None


def _record_from_chapter(
    game: chess.pgn.Game,
    study_id: str,
    lichess_username: str,
    aliases: list[str],
) -> GameRecord | None:
    headers = game.headers
    white = headers.get("White", "")
    black = headers.get("Black", "")
    # Lichess study exports use `ChapterURL`; fall back to `Site` for safety.
    site = headers.get("ChapterURL") or headers.get("Site", "")

    chapter_id = _extract_chapter_id(site, study_id)
    if chapter_id is None:
        return None

    user_color = _resolve_user_color(white, black, lichess_username, aliases)
    if user_color is None:
        # Visible by default so operators see when configured username doesn't match
        # the names recorded in the chapter — common for OTB studies. The fix is
        # usually adding a STUDY_PLAYER_ALIASES entry.
        log.warning(
            "Skipping study chapter %s/%s: user %r (aliases=%s) is neither player "
            "(white=%r, black=%r)",
            study_id, chapter_id, lichess_username, aliases, white, black,
        )
        return None

    pgn_text = str(game) + "\n"
    return GameRecord(
        source="lichess_study",
        source_game_id=f"{study_id}:{chapter_id}",
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


def parse_study_pgn(
    text: str,
    study_id: str,
    lichess_username: str,
    aliases: list[str] | None = None,
) -> list[GameRecord]:
    """Parse a multi-chapter study PGN into a list of GameRecords for chapters
    where the configured user (or any alias) is a player. Pure for unit testing."""
    aliases = aliases or []
    stream = io.StringIO(text)
    records: list[GameRecord] = []
    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        record = _record_from_chapter(game, study_id, lichess_username, aliases)
        if record is not None:
            records.append(record)
    return records


_STUDY_ID_RE = re.compile(r"^[A-Za-z0-9]{8}$")


def _validate_study_id(study_id: str) -> None:
    if not _STUDY_ID_RE.match(study_id):
        raise ValueError(
            f"Invalid Lichess study id {study_id!r}: expected 8 alphanumeric chars."
        )


class LichessStudySource:
    name = "lichess_study"

    def __init__(
        self,
        study_ids: list[str] | None = None,
        aliases: list[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        if study_ids is None:
            study_ids = list(settings.lichess_study_ids)
        if aliases is None:
            aliases = list(settings.study_player_aliases)
        for sid in study_ids:
            _validate_study_id(sid)
        self._study_ids = study_ids
        self._aliases = aliases
        self._client = client

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,  # studies don't have a meaningful "since"
        limit: int | None = None,        # nor a "limit"; caller can slice externally
    ) -> AsyncIterator[GameRecord]:
        if not self._study_ids:
            log.warning(
                "LichessStudySource has no study ids configured; LICHESS_STUDY_IDS is empty."
            )
            return

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        try:
            for study_id in self._study_ids:
                url = f"{LICHESS_API_BASE}/api/study/{study_id}.pgn"
                response = await client.get(
                    url,
                    params={"clocks": "true", "comments": "true"},
                    headers={"Accept": "application/x-chess-pgn"},
                )
                response.raise_for_status()
                for record in parse_study_pgn(
                    response.text, study_id, user.lichess_username, self._aliases
                ):
                    yield record
        finally:
            if owns_client:
                await client.aclose()

    async def fetch_game_by_id(self, game_id: str) -> GameRecord:
        raise NotImplementedError("Single-game fetch not implemented for studies.")
