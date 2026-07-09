"""Generic PGN-header parsing helpers shared by all game sources.

These operate purely on standard PGN tag values (Elo tags that may be "?" or
missing, UTCDate/UTCTime tags) — nothing Lichess- or chess.com-specific.
"""
from __future__ import annotations

from datetime import datetime, timezone

import chess.pgn


def parse_int_header(value: str | None) -> int | None:
    if not value or value == "?":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_played_at(headers: chess.pgn.Headers) -> datetime | None:
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
