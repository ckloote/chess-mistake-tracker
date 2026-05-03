"""Direct unit tests for the heuristic detectors. Each test constructs the
two/three Position rows the relevant detector needs, in memory, with FENs that
make the desired move legal."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.app.analyzers.base import EvalResult
from backend.app.models import Position
from backend.app.services.heuristics import (
    STEP4_CP_DROP,
    _step1,
    _step2,
    _step4,
    _user_view_cp,
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
