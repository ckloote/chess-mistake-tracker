"""Mistake detection: turn analyzed Position rows into Mistake rows.

Implements the algorithm from DESIGN.md §"Mistake Detection". Suppression rules
and severity thresholds come from Settings so they can be tuned per-user later.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.chess_utils import phase, winrate
from backend.app.models import AppSettings, Game, Mistake, Position
from backend.app.services.app_settings import get_app_settings


@dataclass(frozen=True)
class _Thresholds:
    inaccuracy: float
    mistake: float
    blunder: float
    suppress_below: float
    suppress_above_before: float
    suppress_above_after: float

    @classmethod
    def from_app_settings(cls, s: AppSettings) -> "_Thresholds":
        return cls(
            inaccuracy=s.winrate_inaccuracy,
            mistake=s.winrate_mistake,
            blunder=s.winrate_blunder,
            suppress_below=s.suppress_below,
            suppress_above_before=s.suppress_above_before,
            suppress_above_after=s.suppress_above_after,
        )


def _is_suppressed(
    winrate_before: float, winrate_after: float, t: _Thresholds
) -> bool:
    """Apply DESIGN.md's two suppression rules:
    - already losing (both sides below threshold): not "giving away an advantage"
    - still winning despite imprecision (both sides comfortably ahead)
    """
    if winrate_before < t.suppress_below and winrate_after < t.suppress_below:
        return True
    if winrate_before > t.suppress_above_before and winrate_after > t.suppress_above_after:
        return True
    return False


def _eval_cp_for_storage(eval_cp: int | None, mate_in: int | None) -> int | None:
    """Pick a representative cp value to store on the Mistake row. If the
    position is a mate score we collapse it to ±MATE_CP_EQUIVALENT so downstream
    consumers don't need to special-case mate_in."""
    if mate_in is not None:
        if mate_in > 0:
            return winrate.MATE_CP_EQUIVALENT
        if mate_in < 0:
            return -winrate.MATE_CP_EQUIVALENT
        return winrate.MATE_CP_EQUIVALENT
    return eval_cp


def _is_time_pressure(
    pos: Position,
    initial_seconds: int | None,
    median_user_move_ms: float | None,
) -> bool:
    """Time-pressure heuristic per DESIGN.md §"Time-pressure flag":
    - any move under 5 seconds, OR
    - clock under ~10% of starting time, OR
    - move at least 3× faster than the user's median move time in this game.
    """
    if pos.time_spent_ms is not None and pos.time_spent_ms < 5000:
        return True
    if initial_seconds is not None and pos.clock_ms is not None:
        # Floor at 60s (10+0-style games) so very long classical doesn't trigger
        # spuriously, ceiling at 10% of initial for longer time controls.
        threshold_ms = max(60_000, int(initial_seconds * 1000 * 0.1))
        if pos.clock_ms < threshold_ms:
            return True
    if (
        median_user_move_ms is not None
        and pos.time_spent_ms is not None
        and median_user_move_ms > 0
        and pos.time_spent_ms * 3 < median_user_move_ms
    ):
        return True
    return False


def _median_user_move_time_ms(positions: list[Position]) -> float | None:
    times = [p.time_spent_ms for p in positions if p.is_user_move and p.time_spent_ms is not None]
    if not times:
        return None
    return float(statistics.median(times))


def detect_mistakes(session: Session, game: Game) -> list[Mistake]:
    """Re-derive Mistake rows for one game. Idempotent: drops existing first.
    Caller is responsible for committing the session."""
    t = _Thresholds.from_app_settings(get_app_settings(session))

    positions = list(
        session.scalars(
            select(Position).where(Position.game_id == game.id).order_by(Position.ply)
        ).all()
    )
    if len(positions) < 2:
        return []

    by_ply: dict[int, Position] = {p.ply: p for p in positions}

    # Time-control inputs (initial_seconds is needed for the clock-based
    # time-pressure rule; defer parsing to the analysis service helper).
    from backend.app.services.analysis import parse_time_control

    initial_seconds, _ = parse_time_control(game.time_control)
    median_user_move_ms = _median_user_move_time_ms(positions)

    session.execute(delete(Mistake).where(Mistake.game_id == game.id))
    created: list[Mistake] = []

    for pos in positions:
        if not pos.is_user_move or pos.ply == 0:
            continue
        prev = by_ply.get(pos.ply - 1)
        if prev is None:
            continue

        wr_before = winrate.winrate_for_color(prev.eval_cp, prev.mate_in, game.user_color)
        wr_after = winrate.winrate_for_color(pos.eval_cp, pos.mate_in, game.user_color)
        drop = winrate.winrate_drop(wr_before, wr_after)
        if drop is None or drop <= 0:
            continue

        severity = winrate.severity_for_drop(drop, t.inaccuracy, t.mistake, t.blunder)
        if severity is None:
            continue
        if _is_suppressed(wr_before, wr_after, t):
            continue

        board_before = chess.Board(prev.fen)
        board_after = chess.Board(pos.fen)

        mistake = Mistake(
            game_id=game.id,
            ply=pos.ply,
            severity=severity,
            eval_before_cp=_eval_cp_for_storage(prev.eval_cp, prev.mate_in),
            eval_after_cp=_eval_cp_for_storage(pos.eval_cp, pos.mate_in),
            winrate_before=wr_before,
            winrate_after=wr_after,
            winrate_drop=drop,
            time_pressure_flag=_is_time_pressure(pos, initial_seconds, median_user_move_ms),
            endgame_flag=phase.is_endgame(board_after),
            transition_flag=phase.detected_transition(board_before, board_after),
        )
        session.add(mistake)
        created.append(mistake)

    return created
