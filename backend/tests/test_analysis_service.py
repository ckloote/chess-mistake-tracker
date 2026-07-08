from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analyzers.base import EvalResult
from backend.app.db import Base
from backend.app.models import Game, Position, User
from backend.app.services.analysis import (
    analyze_game,
    analyze_pending,
    compute_time_spent_ms,
    is_user_move,
)


class _NoOpCloud:
    name = "noop"
    supports_per_position = True

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        return []

    async def analyze_game(self, pgn: str) -> list:
        raise NotImplementedError

SCHOLARS_MATE_PGN = """\
[Event "Test"]
[Site "https://lichess.org/abcd1234"]
[White "alice"]
[Black "configured_user"]
[Result "1-0"]
[TimeControl "300+0"]

1. e4 { [%eval 0.21] [%clk 0:05:00] } e5 { [%eval 0.18] [%clk 0:05:00] }
2. Qh5 { [%eval -0.42] [%clk 0:04:55] } Nc6 { [%eval -0.35] [%clk 0:04:58] }
3. Bc4 { [%eval -0.30] [%clk 0:04:50] } Nf6 { [%eval 9.21] [%clk 0:04:52] }
4. Qxf7# { [%eval #0] [%clk 0:04:48] } 1-0
"""


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user_and_game(db_session: Session) -> tuple[User, Game]:
    user = User(lichess_username="configured_user")
    db_session.add(user)
    db_session.commit()

    game = Game(
        user_id=user.id,
        source="lichess_online",
        source_game_id="abcd1234",
        user_color="black",
        white="alice",
        black="configured_user",
        result="1-0",
        time_control="300+0",
        played_at=datetime(2025, 1, 15, 12, 34, 56, tzinfo=timezone.utc),
        pgn=SCHOLARS_MATE_PGN,
        has_evals=True,
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    return user, game


# ---- Pure helpers --------------------------------------------------------
# (parse_time_control tests live in test_time_control.py with the helper.)

# FENs after white's / black's move from the standard start (mover = the
# opposite of the side-to-move field).
_FEN_AFTER_WHITE = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
_FEN_AFTER_BLACK = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
_FEN_START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_is_user_move_white() -> None:
    assert is_user_move(0, _FEN_START, "white") is False  # ply 0: no move yet
    assert is_user_move(1, _FEN_AFTER_WHITE, "white") is True
    assert is_user_move(2, _FEN_AFTER_BLACK, "white") is False


def test_is_user_move_black() -> None:
    assert is_user_move(0, _FEN_START, "black") is False
    assert is_user_move(1, _FEN_AFTER_WHITE, "black") is False
    assert is_user_move(2, _FEN_AFTER_BLACK, "black") is True


def test_is_user_move_follows_fen_not_ply_parity() -> None:
    """A chapter starting from a custom [FEN] with black to move: ply 1 is a
    BLACK move. Parity would call it white's — the FEN must win."""
    fen_after_black_first = (
        "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    )
    assert is_user_move(1, fen_after_black_first, "black") is True
    assert is_user_move(1, fen_after_black_first, "white") is False


def test_compute_time_spent_first_move_uses_initial_plus_increment() -> None:
    # Initial 300s, no increment, clock after move 1 is 295s -> spent 5000ms.
    assert compute_time_spent_ms(1, 295_000, None, 300, 0) == 5_000
    # With 30s increment, white's first move ending at 295s (clock includes inc) -> spent 35s.
    assert compute_time_spent_ms(1, 295_000, None, 300, 30) == 35_000


def test_compute_time_spent_subsequent_move_uses_prev_same_color_clock() -> None:
    assert compute_time_spent_ms(3, 290_000, 295_000, 300, 0) == 5_000


def test_compute_time_spent_returns_none_when_data_missing() -> None:
    assert compute_time_spent_ms(1, None, None, 300, 0) is None
    assert compute_time_spent_ms(1, 295_000, None, None, 0) is None
    # Negative spent (data anomaly) -> None
    assert compute_time_spent_ms(3, 296_000, 295_000, 300, 0) is None


# ---- Service-level: idempotency, counts, flags ---------------------------

async def test_analyze_game_creates_one_row_per_ply_including_start(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    # Scholars mate = 7 plies played + ply 0 = 8 rows
    assert result.skipped is False
    assert result.positions_created == 8

    rows = db_session.scalars(
        select(Position).where(Position.game_id == game.id).order_by(Position.ply)
    ).all()
    assert [r.ply for r in rows] == list(range(8))


async def test_analyze_game_sets_is_user_move_for_black(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    rows = db_session.scalars(
        select(Position).where(Position.game_id == game.id).order_by(Position.ply)
    ).all()
    # User is black -> even plies > 0 are user moves
    assert [r.is_user_move for r in rows] == [
        False, False, True, False, True, False, True, False
    ]


async def test_analyze_game_is_idempotent(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    first = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    second = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert first.positions_created == second.positions_created == 8
    rows = db_session.scalars(select(Position).where(Position.game_id == game.id)).all()
    assert len(rows) == 8  # no duplicates after re-run


async def test_analyze_game_skips_when_no_evals(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    game.has_evals = False
    db_session.commit()
    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert result.skipped is True
    assert result.positions_created == 0
    assert "has_evals" in (result.reason or "")


async def test_analyze_game_populates_clock_and_time_spent(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    rows = db_session.scalars(
        select(Position).where(Position.game_id == game.id).order_by(Position.ply)
    ).all()
    # Move 1 (white e4): clock dropped 300->300 (instant) -> 0 ms spent
    assert rows[1].clock_ms == 300_000
    assert rows[1].time_spent_ms == 0
    # Move 3 (white Qh5): white had 300s, now 295s -> spent 5_000ms
    assert rows[3].time_spent_ms == 5_000


# ---- Custom-[FEN] starts (OTB study chapters picked up mid-game) ----------

# Position after 1. e4 e5 2. Qh5 — BLACK to move, so ply 1 of this chapter is
# a black move and ply parity would invert every attribution.
FEN_START_PGN = """\
[Event "OTB study"]
[Site "https://lichess.org/study/stdy0001/chap0001"]
[White "alice"]
[Black "configured_user"]
[Result "1-0"]
[SetUp "1"]
[FEN "rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2"]
[TimeControl "300+0"]

2... Nc6 { [%eval -0.35] [%clk 0:04:58] } 3. Bc4 { [%eval -0.30] [%clk 0:04:50] }
3... Nf6 { [%eval 9.21] [%clk 0:04:52] } 4. Qxf7# { [%clk 0:04:48] } 1-0
"""


@pytest.fixture()
def fen_start_game(db_session: Session) -> Game:
    user = User(lichess_username="configured_user")
    db_session.add(user)
    db_session.commit()
    game = Game(
        user_id=user.id,
        source="lichess_study",
        source_game_id="stdy0001:chap0001",
        user_color="black",
        white="alice",
        black="configured_user",
        result="1-0",
        time_control="300+0",
        pgn=FEN_START_PGN,
        has_evals=True,
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)
    return game


async def test_fen_start_chapter_attributes_moves_by_fen(
    db_session: Session, fen_start_game: Game
) -> None:
    """Black moves first in this chapter (plies 1 and 3). The user is black,
    so exactly those plies are user moves — parity would say 2 and 4."""
    await analyze_game(db_session, fen_start_game, cloud_analyzer=_NoOpCloud())
    rows = db_session.scalars(
        select(Position).where(Position.game_id == fen_start_game.id).order_by(Position.ply)
    ).all()
    assert [r.is_user_move for r in rows] == [False, True, False, True, False]


async def test_fen_start_chapter_attributes_clocks_by_fen(
    db_session: Session, fen_start_game: Game
) -> None:
    """Clock deltas must diff against the mover's own previous clock. With a
    black-first start: black 300->298->292, white 300->290->288."""
    await analyze_game(db_session, fen_start_game, cloud_analyzer=_NoOpCloud())
    rows = db_session.scalars(
        select(Position).where(Position.game_id == fen_start_game.id).order_by(Position.ply)
    ).all()
    assert rows[1].time_spent_ms == 2_000   # black Nc6: 300s -> 298s
    assert rows[2].time_spent_ms == 10_000  # white Bc4: 300s -> 290s
    assert rows[3].time_spent_ms == 6_000   # black Nf6: 298s -> 292s
    assert rows[4].time_spent_ms == 2_000   # white Qxf7#: 290s -> 288s


# ---- analyze_pending: force=True backfill --------------------------------

async def test_analyze_pending_default_skips_already_analyzed(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    # First pass — runs because analyzed_at is null.
    first = await analyze_pending(db_session, cloud_analyzer=_NoOpCloud())
    assert len(first) == 1
    assert first[0].game_id == game.id

    # Second pass with default force=False — no work, because the game is
    # now flagged as analyzed.
    second = await analyze_pending(db_session, cloud_analyzer=_NoOpCloud())
    assert second == []


async def test_analyze_pending_force_reruns_analyzed_games(
    db_session: Session, user_and_game: tuple[User, Game]
) -> None:
    _, game = user_and_game
    await analyze_pending(db_session, cloud_analyzer=_NoOpCloud())

    forced = await analyze_pending(
        db_session, cloud_analyzer=_NoOpCloud(), force=True
    )
    assert len(forced) == 1
    assert forced[0].game_id == game.id
    assert forced[0].skipped is False
    # analyze_game is idempotent — same position count as the first run.
    assert forced[0].positions_created == 8
