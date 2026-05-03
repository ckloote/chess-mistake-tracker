from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base
from backend.app.models import Game, Mistake, User
from backend.app.services.analysis import analyze_game

# Scholars mate. User is black. Black plays Nf6?? on ply 6 (responding to Bc4),
# losing to 4. Qxf7#. The eval before Nf6 is -30 (slight black edge), after Nf6
# is +921 (white winning). Drop from black's view ≈ 50 -> blunder.
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

# A constructed already-losing PGN: black is at -800cp throughout and makes
# moves that drop further. Suppression should fire (both before and after
# below the suppress_below threshold of 30).
ALREADY_LOSING_PGN = """\
[Event "Test"]
[Site "https://lichess.org/already00"]
[White "alice"]
[Black "configured_user"]
[Result "1-0"]
[TimeControl "300+0"]

1. e4 { [%eval 8.0] [%clk 0:05:00] } e5 { [%eval 8.5] [%clk 0:05:00] }
2. Nf3 { [%eval 9.0] [%clk 0:04:55] } Nc6 { [%eval 9.5] [%clk 0:04:58] } 1-0
"""

# Constructed PGN where white is already crushing throughout and stays winning
# — suppress_above_before=90 / suppress_above_after=80 should fire.
ALREADY_WINNING_PGN = """\
[Event "Test"]
[Site "https://lichess.org/winning00"]
[White "configured_user"]
[Black "alice"]
[Result "1-0"]
[TimeControl "300+0"]

1. e4 { [%eval 9.5] [%clk 0:05:00] } e5 { [%eval 9.5] [%clk 0:05:00] }
2. Nf3 { [%eval 9.0] [%clk 0:04:55] } Nc6 { [%eval 9.0] [%clk 0:04:58] } 1-0
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


def _make_game(db: Session, pgn: str, user_color: str, source_id: str) -> Game:
    user = db.scalar(select(User).where(User.lichess_username == "configured_user"))
    if user is None:
        user = User(lichess_username="configured_user")
        db.add(user)
        db.commit()

    game = Game(
        user_id=user.id,
        source="lichess_online",
        source_game_id=source_id,
        user_color=user_color,
        white="alice" if user_color == "black" else "configured_user",
        black="configured_user" if user_color == "black" else "alice",
        result="1-0",
        time_control="300+0",
        played_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        pgn=pgn,
        has_evals=True,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


# ---- Detection happy path -------------------------------------------------

async def test_scholars_mate_flags_one_blunder_on_nf6(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")

    result = await analyze_game(db_session, game)
    assert result.mistakes_detected == 1

    mistakes = db_session.scalars(
        select(Mistake).where(Mistake.game_id == game.id).order_by(Mistake.ply)
    ).all()
    (m,) = mistakes
    assert m.severity == "blunder"
    assert m.ply == 6  # 3...Nf6
    assert m.winrate_drop > 20.0
    # Black's winrate before should be > 50 (they were slightly better at -30cp)
    assert m.winrate_before > 50.0
    # And below 5 after, since white now mates next move.
    assert m.winrate_after < 5.0


async def test_color_flips_for_white_user(db_session: Session) -> None:
    """The same scholars-mate PGN, but with the user playing as white. Black's
    Nf6 (ply 6) was the user's blunder when user was black — that ply must NOT
    be flagged when user is white. (White's own Qh5 is a known dubious move
    rated as a small inaccuracy by Lichess; we just assert no blunder.)"""
    pgn = SCHOLARS_MATE_PGN.replace('[White "alice"]\n[Black "configured_user"]', '[White "configured_user"]\n[Black "alice"]')
    game = _make_game(db_session, pgn, "white", "alt00000")

    await analyze_game(db_session, game)
    mistakes = db_session.scalars(select(Mistake).where(Mistake.game_id == game.id)).all()
    plies = {m.ply for m in mistakes}
    severities = {m.severity for m in mistakes}
    assert 6 not in plies  # the original blunder belongs to black, not white
    assert "blunder" not in severities


async def test_suppression_already_losing(db_session: Session) -> None:
    """Black is at ~-800cp throughout; their winrate stays below ~5%. Even if
    drops technically exceed thresholds they should be suppressed because the
    user isn't 'giving away' anything — they were already lost."""
    game = _make_game(db_session, ALREADY_LOSING_PGN, "black", "lose0000")

    result = await analyze_game(db_session, game)
    assert result.mistakes_detected == 0


async def test_suppression_still_winning(db_session: Session) -> None:
    """White at +900cp stays at +900cp. No real loss of advantage — suppress."""
    game = _make_game(db_session, ALREADY_WINNING_PGN, "white", "win00000")

    result = await analyze_game(db_session, game)
    assert result.mistakes_detected == 0


async def test_detect_is_idempotent(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    first = await analyze_game(db_session, game)
    second = await analyze_game(db_session, game)
    assert first.mistakes_detected == second.mistakes_detected == 1
    rows = db_session.scalars(select(Mistake).where(Mistake.game_id == game.id)).all()
    assert len(rows) == 1


async def test_blunder_mistake_has_endgame_flag_false_in_opening(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game)

    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    assert m.endgame_flag is False  # 6 plies in, all material on board
