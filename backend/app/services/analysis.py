"""Analysis pipeline: take a Game with embedded evals, populate Position rows."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.analyzers.base import PositionEval
from backend.app.analyzers.lichess_pgn import LichessPgnEvalAnalyzer
from backend.app.models import Game, Position


@dataclass(frozen=True)
class AnalysisResult:
    game_id: int
    positions_created: int
    skipped: bool
    reason: str | None = None


_TC_RE = re.compile(r"^\s*(\d+)\s*\+\s*(\d+)\s*$")


def parse_time_control(tc: str | None) -> tuple[int | None, int | None]:
    """`"300+0"` -> (300, 0). Anything non-standard (OTB, correspondence,
    empty) -> (None, None) — caller treats those plies as unmeasurable."""
    if not tc:
        return None, None
    m = _TC_RE.match(tc)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def is_user_move(ply: int, user_color: str) -> bool:
    """True iff the move that produced ply N was played by the configured user.
    ply 0 is the starting position (no move) and is never a user move."""
    if ply <= 0:
        return False
    if user_color == "white":
        return ply % 2 == 1
    if user_color == "black":
        return ply % 2 == 0
    return False


def compute_time_spent_ms(
    ply: int,
    clock_ms: int | None,
    prev_same_color_clock_ms: int | None,
    initial_seconds: int | None,
    increment_seconds: int | None,
) -> int | None:
    """Time the moving player spent on this ply, in ms. None if any input
    needed is missing. Negative results are returned as None (data anomaly)."""
    if clock_ms is None:
        return None
    if increment_seconds is None:
        increment_seconds = 0
    if prev_same_color_clock_ms is None:
        # First move for this color: start clock = initial_seconds.
        if initial_seconds is None:
            return None
        prev_same_color_clock_ms = initial_seconds * 1000
    spent = prev_same_color_clock_ms + increment_seconds * 1000 - clock_ms
    return spent if spent >= 0 else None


def _to_position_rows(
    game: Game, position_evals: list[PositionEval]
) -> list[Position]:
    initial_seconds, increment_seconds = parse_time_control(game.time_control)

    # Track each color's most recent recorded clock so we can diff.
    last_white_clock: int | None = None
    last_black_clock: int | None = None

    rows: list[Position] = []
    for pe in position_evals:
        # Even ply > 0 = black just moved; odd ply = white just moved.
        is_white_move = pe.ply > 0 and pe.ply % 2 == 1
        is_black_move = pe.ply > 0 and pe.ply % 2 == 0

        prev_clock = last_white_clock if is_white_move else last_black_clock if is_black_move else None
        time_spent = (
            compute_time_spent_ms(pe.ply, pe.clock_ms, prev_clock, initial_seconds, increment_seconds)
            if pe.ply > 0
            else None
        )

        if is_white_move and pe.clock_ms is not None:
            last_white_clock = pe.clock_ms
        if is_black_move and pe.clock_ms is not None:
            last_black_clock = pe.clock_ms

        rows.append(
            Position(
                game_id=game.id,
                ply=pe.ply,
                fen=pe.fen,
                san=pe.san,
                uci=pe.uci,
                is_user_move=is_user_move(pe.ply, game.user_color),
                eval_cp=pe.eval_cp,
                mate_in=pe.mate_in,
                clock_ms=pe.clock_ms,
                time_spent_ms=time_spent,
            )
        )
    return rows


async def analyze_game(session: Session, game: Game) -> AnalysisResult:
    """Run the analyzer for one game. Idempotent: drops + recreates Position
    rows. Skips silently if has_evals is False (caller should surface)."""
    if not game.has_evals:
        return AnalysisResult(
            game_id=game.id,
            positions_created=0,
            skipped=True,
            reason="has_evals=False; request analysis on Lichess and re-import.",
        )

    analyzer = LichessPgnEvalAnalyzer()
    position_evals = await analyzer.analyze_game(game.pgn)
    if not position_evals:
        return AnalysisResult(
            game_id=game.id, positions_created=0, skipped=True, reason="PGN parse failed."
        )

    session.execute(delete(Position).where(Position.game_id == game.id))
    rows = _to_position_rows(game, position_evals)
    session.add_all(rows)
    game.analyzed_at = datetime.now(tz=timezone.utc)
    session.commit()

    return AnalysisResult(game_id=game.id, positions_created=len(rows), skipped=False)


async def analyze_pending(session: Session) -> list[AnalysisResult]:
    """Run analysis on every has_evals=true game that hasn't been analyzed yet."""
    games = session.scalars(
        select(Game).where(Game.has_evals.is_(True), Game.analyzed_at.is_(None))
    ).all()
    return [await analyze_game(session, g) for g in games]
