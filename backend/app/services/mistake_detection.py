"""Mistake detection: turn analyzed Position rows into Mistake rows.

Implements the algorithm from DESIGN.md §"Mistake Detection". Suppression rules
and severity thresholds come from Settings so they can be tuned per-user later.

Re-analysis is classification-preserving (DESIGN.md §"Re-analysis semantics"):
existing Mistake rows are reconciled by ply rather than dropped and recreated,
so the user's classified_step / classified_awareness / user_notes survive
re-running detection with new thresholds or refreshed evals.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.chess_utils import phase, winrate
from backend.app.chess_utils.time_control import parse_time_control
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
    winrate_before: float, winrate_after: float, severity: str, t: _Thresholds
) -> bool:
    """Apply DESIGN.md's two suppression rules:
    - already losing (both sides below threshold): not "giving away an advantage"
    - still winning despite imprecision (both sides comfortably ahead)

    The "still winning" rule is intentionally limited to `inaccuracy`-severity
    slips: a mistake or blunder is instructive even when you stay ahead (you
    gave back real, learnable advantage), whereas a minor imprecision while
    comfortably winning is the noise the user doesn't want in the queue.
    """
    if winrate_before < t.suppress_below and winrate_after < t.suppress_below:
        return True
    if (
        severity == "inaccuracy"
        and winrate_before > t.suppress_above_before
        and winrate_after > t.suppress_above_after
    ):
        return True
    return False


def _eval_cp_for_storage(
    eval_cp: int | None, mate_in: int | None, fen: str | None = None
) -> int | None:
    """Pick a representative cp value to store on the Mistake row. If the
    position is a mate score we collapse it to ±MATE_CP_EQUIVALENT so downstream
    consumers don't need to special-case mate_in. `fen` disambiguates a
    delivered mate (mate_in == 0), whose sign is lost in parsing."""
    if mate_in is not None:
        if mate_in > 0:
            return winrate.MATE_CP_EQUIVALENT
        if mate_in < 0:
            return -winrate.MATE_CP_EQUIVALENT
        return winrate.mate_zero_white_view_cp(fen)
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
        # Low-clock threshold: 10% of the starting time (60s for a 10+0 game),
        # scaled in BOTH directions. The old max(60s, …) floor meant a third
        # of every 3+0 blitz game counted as "time pressure".
        threshold_ms = int(initial_seconds * 1000 * 0.1)
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


@dataclass(frozen=True)
class DetectionResult:
    """Outcome of one reconcile pass.

    `mistakes` holds every row that the *current* detection rules flag (both
    newly created and updated-in-place); it's what the heuristic suggestion
    pass should run over. Classified rows that the current rules no longer
    flag are kept in the DB but deliberately NOT in this list — their old
    suggestion/best-move stay frozen alongside their classification.
    """

    mistakes: list[Mistake] = field(default_factory=list)
    new: int = 0
    updated: int = 0
    removed: int = 0  # unclassified rows deleted (no longer detected)
    preserved: int = 0  # classified rows kept although no longer detected


def detect_mistakes(session: Session, game: Game) -> DetectionResult:
    """Re-derive Mistake rows for one game, reconciling against existing rows
    by ply so re-analysis is classification-preserving:

    - detected ply with no existing row     -> create
    - detected ply with an existing row     -> update detection fields in place
      (classification fields are never touched; auto-flags are refreshed only
      while the row is unclassified — once classified, the user confirmed or
      toggled the flags at save time and their version wins)
    - existing row no longer detected       -> delete if unclassified, keep if
      classified (same policy scripts/retune_suppression.py established: a
      hand-classified mistake is never destroyed by a rules change)

    Idempotent. Caller is responsible for committing the session."""
    t = _Thresholds.from_app_settings(get_app_settings(session))

    positions = list(
        session.scalars(
            select(Position).where(Position.game_id == game.id).order_by(Position.ply)
        ).all()
    )
    if len(positions) < 2:
        return DetectionResult()

    by_ply: dict[int, Position] = {p.ply: p for p in positions}

    # Time-control inputs (initial_seconds is needed for the clock-based
    # time-pressure rule).
    initial_seconds, _ = parse_time_control(game.time_control)
    median_user_move_ms = _median_user_move_time_ms(positions)

    existing: dict[int, Mistake] = {
        m.ply: m
        for m in session.scalars(
            select(Mistake).where(Mistake.game_id == game.id)
        ).all()
    }

    detected: list[Mistake] = []
    detected_plies: set[int] = set()
    new = updated = 0

    for pos in positions:
        if not pos.is_user_move or pos.ply == 0:
            continue
        prev = by_ply.get(pos.ply - 1)
        if prev is None:
            continue

        wr_before = winrate.winrate_for_color(
            prev.eval_cp, prev.mate_in, game.user_color, fen=prev.fen
        )
        wr_after = winrate.winrate_for_color(
            pos.eval_cp, pos.mate_in, game.user_color, fen=pos.fen
        )
        drop = winrate.winrate_drop(wr_before, wr_after)
        if drop is None or drop <= 0:
            continue

        severity = winrate.severity_for_drop(drop, t.inaccuracy, t.mistake, t.blunder)
        if severity is None:
            continue
        if _is_suppressed(wr_before, wr_after, severity, t):
            continue

        board_before = chess.Board(prev.fen)
        board_after = chess.Board(pos.fen)

        time_pressure = _is_time_pressure(pos, initial_seconds, median_user_move_ms)
        endgame = phase.is_endgame(board_after)
        transition = phase.detected_transition(board_before, board_after)

        mistake = existing.get(pos.ply)
        if mistake is None:
            mistake = Mistake(
                game_id=game.id,
                ply=pos.ply,
                severity=severity,
                eval_before_cp=_eval_cp_for_storage(prev.eval_cp, prev.mate_in, prev.fen),
                eval_after_cp=_eval_cp_for_storage(pos.eval_cp, pos.mate_in, pos.fen),
                winrate_before=wr_before,
                winrate_after=wr_after,
                winrate_drop=drop,
                time_pressure_flag=time_pressure,
                endgame_flag=endgame,
                transition_flag=transition,
            )
            session.add(mistake)
            new += 1
        else:
            mistake.severity = severity
            mistake.eval_before_cp = _eval_cp_for_storage(prev.eval_cp, prev.mate_in, prev.fen)
            mistake.eval_after_cp = _eval_cp_for_storage(pos.eval_cp, pos.mate_in, pos.fen)
            mistake.winrate_before = wr_before
            mistake.winrate_after = wr_after
            mistake.winrate_drop = drop
            if mistake.classified_at is None:
                mistake.time_pressure_flag = time_pressure
                mistake.endgame_flag = endgame
                mistake.transition_flag = transition
            updated += 1
        detected.append(mistake)
        detected_plies.add(pos.ply)

    removed = preserved = 0
    for ply, row in existing.items():
        if ply in detected_plies:
            continue
        if row.classified_at is not None:
            preserved += 1
            continue
        session.delete(row)
        removed += 1

    return DetectionResult(
        mistakes=detected,
        new=new,
        updated=updated,
        removed=removed,
        preserved=preserved,
    )
