"""Direct unit tests for the heuristic detectors. Each test constructs the
two/three Position rows the relevant detector needs, in memory, with FENs that
make the desired move legal."""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from backend.app.analyzers.base import EvalResult
from backend.app.models import Game, Mistake, Position, User
from backend.app.services.heuristics import (
    STEP4_CP_DROP,
    _step1,
    _step2,
    _step4,
    _user_view_cp,
    _uci_to_san,
    assign_heuristic_suggestions,
)


def _pos(ply: int, fen: str, uci: str, eval_cp: int | None = None, mate_in: int | None = None) -> Position:
    """Build a Position row in memory. We don't persist it, so we don't need
    every column to be sensible — only the fields the detectors read."""
    return Position(
        ply=ply,
        fen=fen,
        uci=uci,
        san=None,
        is_user_move=(ply % 2 == 1),
        eval_cp=eval_cp,
        mate_in=mate_in,
        clock_ms=None,
        time_spent_ms=None,
    )


# -- _user_view_cp ----------------------------------------------------------

def test_user_view_cp_flips_for_black() -> None:
    assert _user_view_cp(200, None, "white") == 200
    assert _user_view_cp(200, None, "black") == -200


def test_user_view_cp_collapses_mate() -> None:
    assert _user_view_cp(None, 3, "white") == 1000
    assert _user_view_cp(None, -3, "white") == -1000
    assert _user_view_cp(None, -3, "black") == 1000


def test_user_view_cp_returns_none_when_no_eval() -> None:
    assert _user_view_cp(None, None, "white") is None


# -- Step 4 -----------------------------------------------------------------

# White (user) just dropped a queen on c3. Black to move; Qxc3 captures it.
POS_AFTER_USER_DROPS_QUEEN = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2Q5/PPPP1PPP/RNB1KBNR b KQkq - 0 1"
NXT_AFTER_BLACK_CAPTURES = "r1b1kb1r/pppp1ppp/2n2n2/4p3/4P3/2q5/PPPP1PPP/RNB1KBNR w KQkq - 0 2"


def test_step4_fires_on_forcing_capture_with_big_eval_drop() -> None:
    pos = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    nxt = _pos(ply=6, fen=NXT_AFTER_BLACK_CAPTURES, uci="d8c3", eval_cp=-880)

    fired, debug = _step4(pos, nxt, user_color="white")
    assert fired is True
    assert debug["forcing"] is True
    assert debug["cp_drop"] >= STEP4_CP_DROP


def test_step4_does_not_fire_when_opp_response_non_forcing() -> None:
    # Same starting position, but instead of capturing the user's queen, black
    # plays a quiet developing move (Nb8-d7 won't be legal here; use a8->b8 just
    # for shape — any non-capture, non-check uci on a legal move suffices).
    pos = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    # Black plays Nf6-g8 retreating, a quiet move that reaches a different FEN;
    # we don't actually need the resulting fen to match — _step4 only checks
    # forcing-ness against the pre-opp board.
    nxt = _pos(ply=6, fen=POS_AFTER_USER_DROPS_QUEEN, uci="f6g8", eval_cp=10)

    fired, debug = _step4(pos, nxt, user_color="white")
    assert fired is False
    assert debug["forcing"] is False


def test_step4_does_not_fire_when_drop_is_small() -> None:
    # Capture happens, but the captured piece was already accounted for in the
    # eval (eval barely changes). Below threshold -> no Step 4.
    pos = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    nxt = _pos(ply=6, fen=NXT_AFTER_BLACK_CAPTURES, uci="d8c3", eval_cp=-50)

    fired, debug = _step4(pos, nxt, user_color="white")
    assert fired is False
    assert debug["forcing"] is True
    assert debug["cp_drop"] < STEP4_CP_DROP


def test_step4_skips_when_no_next_position() -> None:
    pos = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    fired, debug = _step4(pos, None, user_color="white")
    assert fired is False


# -- Step 2 -----------------------------------------------------------------

# Italian: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4 (Evans Gambit), black to move.
# Best move (per opening theory) is Bxb4 (capturing the pawn) — forcing.
POS_BEFORE_BLACK_CHOICE = "r1bqk1nr/pppp1ppp/2n5/2b1p3/1PB1P3/5N2/P1PP1PPP/RNBQK2R b KQkq - 0 4"
# Suppose black played a quiet move (Nf6) instead — that's the user's M_user.
USER_PLAYED_NF6_FROM_ABOVE = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/1PB1P3/5N2/P1PP1PPP/RNBQK2R w KQkq - 1 5"


def test_step2_fires_when_best_is_forcing_user_isnt_and_winrate_high() -> None:
    prev = _pos(ply=7, fen=POS_BEFORE_BLACK_CHOICE, uci="b2b4", eval_cp=50)
    pos = _pos(ply=8, fen=USER_PLAYED_NF6_FROM_ABOVE, uci="g8f6", eval_cp=80)

    fired, debug = _step2(prev, pos, m_best_uci="c5b4", winrate_before=55.0)
    assert fired is True
    assert debug["m_best_forcing"] is True
    assert debug["m_user_forcing"] is False


def test_step2_does_not_fire_when_user_already_below_50_winrate() -> None:
    prev = _pos(ply=7, fen=POS_BEFORE_BLACK_CHOICE, uci="b2b4", eval_cp=50)
    pos = _pos(ply=8, fen=USER_PLAYED_NF6_FROM_ABOVE, uci="g8f6", eval_cp=80)

    fired, _debug = _step2(prev, pos, m_best_uci="c5b4", winrate_before=42.0)
    assert fired is False


def test_step2_does_not_fire_when_user_move_was_also_forcing() -> None:
    prev = _pos(ply=7, fen=POS_BEFORE_BLACK_CHOICE, uci="b2b4", eval_cp=50)
    # Suppose user played the capture too — both forcing, so it's not "missed."
    pos = _pos(ply=8, fen=USER_PLAYED_NF6_FROM_ABOVE, uci="c5b4", eval_cp=80)

    fired, debug = _step2(prev, pos, m_best_uci="c5b4", winrate_before=55.0)
    assert fired is False
    assert debug["m_user_forcing"] is True


# -- Step 1 -----------------------------------------------------------------

def test_step1_fires_when_best_captures_the_just_moved_piece() -> None:
    # Opponent's move uci ended at c3 (e.g., they moved a piece TO c3).
    # Best response captures on c3.
    prev = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    fired, debug = _step1(prev, m_best_uci="d8c3")
    assert fired is True
    assert debug["m_best_captures_opp_mover"] is True


def test_step1_does_not_fire_when_best_is_unrelated_move() -> None:
    prev = _pos(ply=5, fen=POS_AFTER_USER_DROPS_QUEEN, uci="d1c3", eval_cp=20)
    # Best moves a knight, ignoring the c3 piece.
    fired, debug = _step1(prev, m_best_uci="b8c6")
    assert fired is False
    assert debug["m_best_captures_opp_mover"] is False


# -- Cloud cache helper -----------------------------------------------------

class _StubCloudAnalyzer:
    """Records calls so we can assert caching."""

    def __init__(self, by_fen: dict[str, list[EvalResult]]) -> None:
        self._by_fen = by_fen
        self.calls: list[str] = []

    @property
    def supports_per_position(self) -> bool:
        return True

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        self.calls.append(fen)
        return list(self._by_fen.get(fen, []))


@pytest.fixture()
def cloud_stub() -> _StubCloudAnalyzer:
    return _StubCloudAnalyzer({
        POS_BEFORE_BLACK_CHOICE: [EvalResult(cp=50, mate=None, pv=["c5b4", "f3e5"])],
    })


# -- _uci_to_san -----------------------------------------------------------

def test_uci_to_san_renders_capture_with_check_correctly() -> None:
    # Italian: 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nf6 4.Ng5 d5 5.exd5 Nxd5 6.Nxf7 — Knight
    # captures on f7 forking king and queen. Black to move from this FEN:
    fen = "r1bqkb1r/ppp2Npp/2n5/3np3/2B5/8/PPPP1PPP/RNBQK2R b KQkq - 0 6"
    # Black plays Kxf7 — the king captures the knight (forced).
    assert _uci_to_san(fen, "e8f7") == "Kxf7"


def test_uci_to_san_returns_none_for_illegal_move_in_position() -> None:
    # Starting position. e2e5 is not a legal first move for a pawn.
    starting = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    assert _uci_to_san(starting, "e2e5") is None


def test_uci_to_san_returns_none_for_malformed_inputs() -> None:
    assert _uci_to_san("not a fen", "e2e4") is None
    assert _uci_to_san(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "xyzzy",
    ) is None


# -- assign_heuristic_suggestions: persistence of best move ---------------

# A position where the user (white) just dropped a piece on c3 (queen to c3).
# Cloud will return a non-capturing best move ("a2a3") so Step 4 still fires
# but the cloud value is independent — exactly the scenario we want to make
# sure the persistence path covers.
PREV_FEN_USER_TO_MOVE = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/8/PPPPQPPP/RNB1KBNR w KQkq - 0 1"
POS_AFTER_USER_DROP = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2Q5/PPPP1PPP/RNB1KBNR b KQkq - 1 1"
NXT_AFTER_BLACK_CAPS = "r1b1kb1r/pppp1ppp/2n2n2/4p3/4P3/2q5/PPPP1PPP/RNB1KBNR w KQkq - 0 2"


def _seed_game_with_step4_mistake(db: Session) -> tuple[Game, Mistake, list[Position]]:
    user = User(lichess_username="phaedrus")
    db.add(user)
    db.commit()

    game = Game(
        user_id=user.id,
        source="lichess_online",
        source_game_id="g0000001",
        user_color="white",
        white="phaedrus",
        black="alice",
        result="0-1",
        time_control="300+0",
        played_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        pgn="[Event \"Test\"]\n\n1. e4 *\n",
        has_evals=True,
    )
    db.add(game)
    db.commit()

    # Positions: prev (ply 4, before white's blunder), pos (ply 5, after white's
    # Qe2-c3), nxt (ply 6, after black's Qxc3).
    positions = [
        Position(
            game_id=game.id,
            ply=4,
            fen=PREV_FEN_USER_TO_MOVE,
            san="Nc6",
            uci="b8c6",
            is_user_move=False,
            eval_cp=20,
        ),
        Position(
            game_id=game.id,
            ply=5,
            fen=POS_AFTER_USER_DROP,
            san="Qc3",
            uci="e2c3",
            is_user_move=True,
            eval_cp=20,
        ),
        Position(
            game_id=game.id,
            ply=6,
            fen=NXT_AFTER_BLACK_CAPS,
            san="Qxc3",
            uci="d8c3",
            is_user_move=False,
            eval_cp=-880,
        ),
    ]
    for p in positions:
        db.add(p)
    db.commit()

    mistake = Mistake(
        game_id=game.id,
        ply=5,
        severity="blunder",
        eval_before_cp=20,
        eval_after_cp=-880,
        winrate_before=52.0,
        winrate_after=4.0,
        winrate_drop=48.0,
        time_pressure_flag=False,
        transition_flag=False,
        endgame_flag=False,
    )
    db.add(mistake)
    db.commit()

    return game, mistake, positions


async def test_best_move_persists_even_when_step4_fires(db: Session) -> None:
    """Regression: before this change, Step-4 mistakes never got
    best_move_uci/san populated because the heuristic short-circuited before
    the cloud-eval call."""
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    stub = _StubCloudAnalyzer({
        # Cloud's preferred move from PREV_FEN is Qe2-a6 (non-capture, not the
        # blunder Qe2-c3) — the exact UCI doesn't matter, only that it's a
        # legal move so SAN renders cleanly.
        PREV_FEN_USER_TO_MOVE: [
            EvalResult(cp=20, mate=None, pv=["e2a6", "c6d4"]),
        ],
    })

    await assign_heuristic_suggestions(db, game, [mistake], cloud_analyzer=stub)
    db.commit()
    db.refresh(mistake)

    # Step 4 still fires (opponent's Qxc3 captures and drops eval ≥ 200cp).
    assert mistake.suggested_step == 4
    # AND the cloud-supplied best move was persisted.
    assert mistake.best_move_uci == "e2a6"
    # a6 is empty in this position → quiet queen move, no capture marker.
    assert mistake.best_move_san == "Qa6"
    # The stub was consulted exactly once for prev's FEN.
    assert stub.calls == [PREV_FEN_USER_TO_MOVE]


async def test_best_move_stays_null_when_cloud_returns_nothing(db: Session) -> None:
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    stub = _StubCloudAnalyzer({})  # cloud has no entry for this FEN

    await assign_heuristic_suggestions(db, game, [mistake], cloud_analyzer=stub)
    db.commit()
    db.refresh(mistake)

    assert mistake.suggested_step == 4
    assert mistake.best_move_uci is None
    assert mistake.best_move_san is None


async def test_best_move_san_handled_when_uci_is_illegal_in_position(
    db: Session,
) -> None:
    """If cloud-eval ever returns a move that isn't legal in the position
    (e.g. transposed cache hit), the UCI is still kept (so the UI can try
    to draw the arrow) but SAN renders as None instead of raising."""
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    stub = _StubCloudAnalyzer({
        PREV_FEN_USER_TO_MOVE: [
            EvalResult(cp=0, mate=None, pv=["e2e5"]),  # not legal here
        ],
    })

    await assign_heuristic_suggestions(db, game, [mistake], cloud_analyzer=stub)
    db.commit()
    db.refresh(mistake)

    assert mistake.best_move_uci == "e2e5"
    assert mistake.best_move_san is None


# -- Cloud → local cascade ------------------------------------------------

class _StubLocalAnalyzer:
    """Stand-in for StockfishLocalAnalyzer in tests where we want to
    exercise the cascade logic without spawning a real engine process."""

    name = "stub_local"

    def __init__(self, by_fen: dict[str, list[EvalResult]]) -> None:
        self._by_fen = by_fen
        self.calls: list[str] = []

    @property
    def supports_per_position(self) -> bool:
        return True

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        self.calls.append(fen)
        return list(self._by_fen.get(fen, []))

    async def analyze_game(self, pgn: str) -> list:
        raise NotImplementedError


async def test_local_fills_in_when_cloud_returns_nothing(db: Session) -> None:
    """The whole point of Stockfish-local: when cloud has no entry for a
    position, the local analyzer answers and the best move still lands on
    the Mistake row."""
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    cloud = _StubCloudAnalyzer({})  # cloud knows nothing
    local = _StubLocalAnalyzer({
        PREV_FEN_USER_TO_MOVE: [
            EvalResult(cp=15, mate=None, pv=["e2a6"]),
        ],
    })

    await assign_heuristic_suggestions(
        db, game, [mistake], cloud_analyzer=cloud, local_analyzer=local,
    )
    db.commit()
    db.refresh(mistake)

    assert cloud.calls == [PREV_FEN_USER_TO_MOVE]  # cloud was asked first
    assert local.calls == [PREV_FEN_USER_TO_MOVE]  # local was the fallback
    assert mistake.best_move_uci == "e2a6"
    assert mistake.best_move_san == "Qa6"


async def test_local_not_consulted_when_cloud_has_an_answer(db: Session) -> None:
    """Cascade short-circuits: a cloud hit means no local call, which keeps
    the analyze-pending run fast on positions that ARE in cloud-eval."""
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    cloud = _StubCloudAnalyzer({
        PREV_FEN_USER_TO_MOVE: [EvalResult(cp=10, mate=None, pv=["e2a6"])],
    })
    local = _StubLocalAnalyzer({
        PREV_FEN_USER_TO_MOVE: [EvalResult(cp=99, mate=None, pv=["e2d3"])],
    })

    await assign_heuristic_suggestions(
        db, game, [mistake], cloud_analyzer=cloud, local_analyzer=local,
    )
    db.commit()
    db.refresh(mistake)

    assert cloud.calls == [PREV_FEN_USER_TO_MOVE]
    assert local.calls == []  # never consulted
    assert mistake.best_move_uci == "e2a6"


async def test_no_local_no_problem_when_cloud_empty(db: Session) -> None:
    """Smoke test for the "feature off" default: cloud empty, no local
    provided. The mistake still gets a Step assignment (3 by default) and
    best_move_uci stays None — same as the pre-Stockfish baseline."""
    game, mistake, _ = _seed_game_with_step4_mistake(db)
    cloud = _StubCloudAnalyzer({})

    await assign_heuristic_suggestions(db, game, [mistake], cloud_analyzer=cloud)
    db.commit()
    db.refresh(mistake)

    assert mistake.best_move_uci is None
    # Step 4 still fires from local data, independent of cloud presence.
    assert mistake.suggested_step == 4
