"""Pure-parsing and fetch-behavior tests for the chess.com source.

Parsing tests run against a trimmed real-shaped monthly-archive fixture.
Fetch tests use httpx.MockTransport — no network, no monkeypatching.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from backend.app.models import User
from backend.app.sources.base import RefreshUnsupported, SourceMisconfigured
from backend.app.sources.chesscom import (
    CHESSCOM_API_BASE,
    ChessComSource,
    extract_game_id,
    record_from_archive_game,
)

FIXTURE = Path(__file__).parent / "fixtures" / "chesscom_month.json"


@pytest.fixture()
def month() -> dict:
    return json.loads(FIXTURE.read_text())


def _game(month: dict, game_id_tail: str) -> dict:
    return next(g for g in month["games"] if g["url"].endswith(game_id_tail))


# ---- extract_game_id ---------------------------------------------------------

def test_extract_game_id_keeps_live_or_daily_segment() -> None:
    assert extract_game_id("https://www.chess.com/game/live/140723958581") == (
        "live/140723958581"
    )
    assert extract_game_id("https://www.chess.com/game/daily/747757185") == (
        "daily/747757185"
    )


def test_extract_game_id_rejects_junk() -> None:
    assert extract_game_id(None) is None
    assert extract_game_id("") is None
    assert extract_game_id("https://www.chess.com/member/testuser") is None
    assert extract_game_id("https://www.chess.com/game/") is None


# ---- record_from_archive_game ------------------------------------------------

def test_record_from_live_game_as_white(month: dict) -> None:
    record = record_from_archive_game(_game(month, "live/140723958581"), "TestUser")
    assert record is not None
    assert record.source == "chesscom"
    assert record.source_game_id == "live/140723958581"
    assert record.user_color == "white"
    assert record.white == "TestUser"
    assert record.black == "OpponentOne"
    assert record.result == "1-0"
    assert record.white_elo == 1500
    assert record.black_elo == 1480
    assert record.time_control == "180+2"
    # From the PGN UTCDate/UTCTime headers, not end_time.
    assert record.played_at == datetime(2025, 6, 17, 10, 30, 0, tzinfo=timezone.utc)
    # chess.com PGNs never carry %eval — the F3 local-Stockfish path applies.
    assert record.has_evals is False
    assert "[%clk 0:03:01.9]" in record.pgn


def test_record_from_daily_game_as_black(month: dict) -> None:
    record = record_from_archive_game(_game(month, "daily/747757185"), "TestUser")
    assert record is not None
    assert record.source_game_id == "daily/747757185"
    assert record.user_color == "black"
    assert record.time_control == "1/259200"
    assert record.result == "0-1"


def test_username_match_is_case_insensitive(month: dict) -> None:
    record = record_from_archive_game(_game(month, "live/140723958581"), "TESTUSER")
    assert record is not None
    assert record.user_color == "white"


def test_variant_games_are_skipped(month: dict) -> None:
    assert record_from_archive_game(_game(month, "live/140700000001"), "TestUser") is None


def test_returns_none_when_user_is_neither_player(month: dict) -> None:
    assert record_from_archive_game(_game(month, "live/140723958581"), "no_one") is None


def test_returns_none_when_pgn_missing(month: dict) -> None:
    game = dict(_game(month, "live/140723958581"))
    del game["pgn"]
    assert record_from_archive_game(game, "TestUser") is None


def test_played_at_falls_back_to_end_time(month: dict) -> None:
    game = dict(_game(month, "live/140723958581"))
    game["pgn"] = game["pgn"].replace('[UTCDate "2025.06.17"]\n', "").replace(
        '[UTCTime "10:30:00"]\n', ""
    ).replace('[Date "2025.06.17"]\n', "")
    record = record_from_archive_game(game, "TestUser")
    assert record is not None
    assert record.played_at == datetime.fromtimestamp(
        game["end_time"], tz=timezone.utc
    )


# ---- fetch behavior (httpx.MockTransport, no network) ------------------------

def _make_source(month_payloads: dict[str, dict]) -> ChessComSource:
    """A source whose client serves the archives list plus the given
    month-URL → payload map."""
    archives = {"archives": list(month_payloads)}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert request.headers["User-Agent"].startswith("chess-mistake-tracker")
        if url.endswith("/games/archives"):
            return httpx.Response(200, json=archives)
        if url in month_payloads:
            return httpx.Response(200, json=month_payloads[url])
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ChessComSource(client=client)


def _user(chesscom_username: str | None = "TestUser") -> User:
    return User(lichess_username="configured_user", chesscom_username=chesscom_username)


async def _collect(source: ChessComSource, **kwargs) -> list:
    return [r async for r in source.fetch_recent_games(_user(), **kwargs)]


async def test_fetch_yields_newest_first_across_months(month: dict) -> None:
    may_url = f"{CHESSCOM_API_BASE}/pub/player/TestUser/games/2025/05"
    june_url = f"{CHESSCOM_API_BASE}/pub/player/TestUser/games/2025/06"
    may_game = dict(_game(month, "daily/747757185"))
    may_game["url"] = "https://www.chess.com/game/live/100000000001"
    may_game["end_time"] = 1746100000  # 2025-05-01
    source = _make_source({may_url: {"games": [may_game]}, june_url: month})

    records = await _collect(source)
    # June first (months walked newest-first), and within June the live game
    # (latest end_time) before the daily one; the chess960 game is skipped.
    assert [r.source_game_id for r in records] == [
        "live/140723958581",
        "daily/747757185",
        "live/100000000001",
    ]


async def test_fetch_stops_at_limit(month: dict) -> None:
    url = f"{CHESSCOM_API_BASE}/pub/player/TestUser/games/2025/06"
    source = _make_source({url: month})
    records = await _collect(source, limit=1)
    assert [r.source_game_id for r in records] == ["live/140723958581"]


async def test_fetch_stops_at_since(month: dict) -> None:
    url = f"{CHESSCOM_API_BASE}/pub/player/TestUser/games/2025/06"
    source = _make_source({url: month})
    # Naive datetime is treated as UTC; between the daily game (06-14) and
    # the live game (06-17), so only the live game comes back.
    records = await _collect(source, since=datetime(2025, 6, 16))
    assert [r.source_game_id for r in records] == ["live/140723958581"]


async def test_fetch_requires_chesscom_username() -> None:
    source = ChessComSource()
    with pytest.raises(SourceMisconfigured):
        async for _ in source.fetch_recent_games(_user(chesscom_username=None)):
            pass


async def test_fetch_game_by_id_is_unsupported() -> None:
    source = ChessComSource()
    with pytest.raises(RefreshUnsupported):
        await source.fetch_game_by_id(_user(), "live/140723958581")


# ---- pipeline: chess.com records through ingest + local analysis -------------

async def test_chesscom_records_flow_through_ingest_and_local_analysis(
    month: dict,
) -> None:
    """End-to-end-ish: fixture records persist via ingest(), and the F3
    local-analysis path produces positions with the fractional-second %clk
    values chess.com PGNs carry."""
    from dataclasses import replace

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from backend.app.analyzers.lichess_pgn import parse_pgn_for_positions
    from backend.app.db import Base
    from backend.app.models import Game, Position
    from backend.app.services.analysis import analyze_game
    from backend.app.services.ingestion import ingest

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    try:
        user = _user()
        session.add(user)
        session.commit()

        url = f"{CHESSCOM_API_BASE}/pub/player/TestUser/games/2025/06"
        source = _make_source({url: month})
        result = await ingest(session, user, source)
        assert result.imported == 2  # live + daily; chess960 skipped

        live = session.scalar(
            select(Game).where(Game.source_game_id == "live/140723958581")
        )
        assert live is not None
        assert live.source == "chesscom"
        assert live.has_evals is False

        class _FlatEvalLocal:
            """Whole-game local analyzer that stamps a flat eval on every ply
            — enough to exercise position/clock extraction."""

            name = "fake_local"
            supports_per_position = True

            async def analyze_position(self, fen: str, multipv: int = 1) -> list:
                return []

            async def analyze_game(self, pgn: str) -> list:
                return [
                    replace(pe, eval_cp=0) for pe in parse_pgn_for_positions(pgn)
                ]

        analysis = await analyze_game(session, live, local_analyzer=_FlatEvalLocal())
        assert analysis.skipped is False
        assert analysis.positions_created == 13  # 12 plies + start

        rows = session.scalars(
            select(Position).where(Position.game_id == live.id).order_by(Position.ply)
        ).all()
        # 1. e4 {[%clk 0:03:01.9]} — fractional seconds land in clock_ms.
        assert rows[1].clock_ms == 181_900
        assert rows[2].clock_ms == 181_500
    finally:
        session.close()
        engine.dispose()
