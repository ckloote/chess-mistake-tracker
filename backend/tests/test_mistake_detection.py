from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.analyzers.base import EvalResult
from backend.app.db import Base
from backend.app.models import Game, Mistake, User
from backend.app.services.analysis import analyze_game
from backend.app.services.mistake_detection import _is_suppressed, _Thresholds


_T = _Thresholds(
    inaccuracy=5.0,
    mistake=10.0,
    blunder=20.0,
    suppress_below=30.0,
    suppress_above_before=75.0,
    suppress_above_after=68.0,
)


def test_still_winning_suppresses_inaccuracy_only() -> None:
    # Comfortably ahead, stayed ahead. An inaccuracy here is noise → suppress.
    assert _is_suppressed(83.0, 72.0, "inaccuracy", _T) is True
    # A mistake or blunder in the same band gave back real advantage → keep.
    assert _is_suppressed(83.0, 72.0, "mistake", _T) is False
    assert _is_suppressed(95.0, 74.0, "blunder", _T) is False


def test_already_losing_suppresses_regardless_of_severity() -> None:
    # Both sides below suppress_below: not "giving away" anything you had.
    assert _is_suppressed(10.0, 3.0, "blunder", _T) is True
    assert _is_suppressed(10.0, 3.0, "inaccuracy", _T) is True


def test_contested_position_is_never_suppressed() -> None:
    # 55% -> 45% is a real, learnable slip even if only an inaccuracy.
    assert _is_suppressed(55.0, 45.0, "inaccuracy", _T) is False


class _NoOpCloud:
    """Returns nothing for every position — keeps tests off the network.
    Heuristics fall through to Step 3 / Step 4, which is fine for tests that
    only care about detection counts and severities."""

    name = "noop"
    supports_per_position = True

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        return []

    async def analyze_game(self, pgn: str) -> list:
        raise NotImplementedError

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

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
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

    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
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

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert result.mistakes_detected == 0


async def test_suppression_still_winning(db_session: Session) -> None:
    """White at +900cp stays at +900cp. No real loss of advantage — suppress."""
    game = _make_game(db_session, ALREADY_WINNING_PGN, "white", "win00000")

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert result.mistakes_detected == 0


async def test_detect_is_idempotent(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    first = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    second = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert first.mistakes_detected == second.mistakes_detected == 1
    rows = db_session.scalars(select(Mistake).where(Mistake.game_id == game.id)).all()
    assert len(rows) == 1


async def test_blunder_mistake_has_endgame_flag_false_in_opening(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    assert m.endgame_flag is False  # 6 plies in, all material on board


# ---- Classification-preserving re-analysis ---------------------------------
# DESIGN.md §"Re-analysis semantics": re-running detection reconciles Mistake
# rows by ply instead of dropping them, so user classifications survive.

def _classify(db: Session, m: Mistake, *, step: int = 4) -> None:
    m.classified_step = step
    m.classified_awareness = "didnt_see_it"
    m.user_notes = "hung the f7 fork"
    m.classified_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
    db.commit()


async def test_reanalysis_preserves_classification_in_place(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    _classify(db_session, m)
    original_id = m.id

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    rows = db_session.scalars(select(Mistake).where(Mistake.game_id == game.id)).all()
    (row,) = rows
    assert row.id == original_id  # updated in place, not recreated
    assert row.classified_step == 4
    assert row.classified_awareness == "didnt_see_it"
    assert row.user_notes == "hung the f7 fork"
    assert row.classified_at is not None
    # Detection fields still re-derived on the surviving row.
    assert row.severity == "blunder"
    assert result.mistakes_new == 0
    assert result.mistakes_updated == 1
    assert result.mistakes_removed == 0
    assert result.mistakes_preserved == 0


async def test_reanalysis_refreshes_detection_fields_on_surviving_row(
    db_session: Session,
) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    # Corrupt detection-derived fields; re-analysis must restore them.
    m.severity = "inaccuracy"
    m.winrate_drop = 1.0
    db_session.commit()

    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    db_session.refresh(m)
    assert m.severity == "blunder"
    assert m.winrate_drop > 20.0


async def test_reanalysis_keeps_user_toggled_flags_once_classified(
    db_session: Session,
) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    auto_time_pressure = m.time_pressure_flag
    # User flips a tag at classification time; their version must win.
    _classify(db_session, m)
    m.time_pressure_flag = not auto_time_pressure
    db_session.commit()

    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    db_session.refresh(m)
    assert m.time_pressure_flag == (not auto_time_pressure)


async def test_reanalysis_resets_flags_while_unclassified(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    m = db_session.scalar(select(Mistake).where(Mistake.game_id == game.id))
    assert m is not None
    auto_time_pressure = m.time_pressure_flag
    # Flag toggled but never classified: auto-detection wins on re-run.
    m.time_pressure_flag = not auto_time_pressure
    db_session.commit()

    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    db_session.refresh(m)
    assert m.time_pressure_flag == auto_time_pressure


async def test_reanalysis_removes_stale_unclassified_rows(db_session: Session) -> None:
    """A row the current rules no longer flag (e.g. after tightening
    thresholds) is deleted — but only because it's unclassified."""
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    stale = Mistake(
        game_id=game.id,
        ply=2,  # 1...e5 — not a detectable mistake in this PGN
        severity="inaccuracy",
        winrate_before=55.0,
        winrate_after=49.0,
        winrate_drop=6.0,
    )
    db_session.add(stale)
    db_session.commit()

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    plies = {m.ply for m in db_session.scalars(select(Mistake).where(Mistake.game_id == game.id))}
    assert plies == {6}
    assert result.mistakes_removed == 1
    assert result.mistakes_preserved == 0


async def test_reanalysis_keeps_stale_classified_rows(db_session: Session) -> None:
    """A classified row is never deleted, even when the current rules no
    longer flag its ply — same policy as scripts/retune_suppression.py."""
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    stale = Mistake(
        game_id=game.id,
        ply=2,
        severity="inaccuracy",
        winrate_before=55.0,
        winrate_after=49.0,
        winrate_drop=6.0,
        classified_step=3,
        classified_awareness="got_it_wrong",
        classified_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    db_session.add(stale)
    db_session.commit()

    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())

    rows = {
        m.ply: m
        for m in db_session.scalars(select(Mistake).where(Mistake.game_id == game.id))
    }
    assert set(rows) == {2, 6}
    assert rows[2].classified_step == 3
    # The stale row keeps its frozen detection fields too — it reflects the
    # rules under which it was classified.
    assert rows[2].severity == "inaccuracy"
    assert result.mistakes_detected == 1  # only ply 6 is a current detection
    assert result.mistakes_preserved == 1
    assert result.mistakes_removed == 0


async def test_first_analysis_counters(db_session: Session) -> None:
    game = _make_game(db_session, SCHOLARS_MATE_PGN, "black", "abcd1234")
    result = await analyze_game(db_session, game, cloud_analyzer=_NoOpCloud())
    assert result.mistakes_new == result.mistakes_detected == 1
    assert result.mistakes_updated == 0
    assert result.mistakes_removed == 0
    assert result.mistakes_preserved == 0
