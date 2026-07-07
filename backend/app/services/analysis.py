"""Analysis pipeline: take a Game with embedded evals, populate Position rows."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.analyzers.base import Analyzer, PositionEval
from backend.app.analyzers.lichess_cloud import LichessCloudEvalAnalyzer
from backend.app.analyzers.lichess_pgn import LichessPgnEvalAnalyzer
from backend.app.models import Game, Position
from backend.app.services.heuristics import assign_heuristic_suggestions
from backend.app.services.mistake_detection import detect_mistakes


@dataclass(frozen=True)
class AnalysisResult:
    game_id: int
    positions_created: int
    mistakes_detected: int
    skipped: bool
    reason: str | None = None
    # Reconcile counters from classification-preserving re-analysis
    # (DESIGN.md §"Re-analysis semantics"). On a first analysis new ==
    # mistakes_detected and the rest are 0.
    mistakes_new: int = 0
    mistakes_updated: int = 0
    mistakes_removed: int = 0  # stale unclassified rows deleted
    mistakes_preserved: int = 0  # stale classified rows kept


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


def mover_color(fen: str) -> str | None:
    """Color of the player who made the move *producing* this position — the
    opposite of the FEN's side-to-move. None for a malformed FEN."""
    parts = fen.split()
    if len(parts) < 2 or parts[1] not in ("w", "b"):
        return None
    return "black" if parts[1] == "w" else "white"


def is_user_move(ply: int, fen: str, user_color: str) -> bool:
    """True iff the move that produced this position was played by the
    configured user. ply 0 is the starting position (no move) and is never a
    user move.

    The mover is derived from the position's FEN, NOT from ply parity: study
    chapters can start from a custom [FEN] with black to move (an OTB game
    picked up mid-way), where parity would invert every attribution."""
    if ply <= 0:
        return False
    return mover_color(fen) == user_color


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
        # Who moved is read off the FEN (mover = opposite of side-to-move),
        # not off ply parity — see is_user_move for why.
        mover = mover_color(pe.fen) if pe.ply > 0 else None
        is_white_move = mover == "white"
        is_black_move = mover == "black"

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
                is_user_move=is_user_move(pe.ply, pe.fen, game.user_color),
                eval_cp=pe.eval_cp,
                mate_in=pe.mate_in,
                clock_ms=pe.clock_ms,
                time_spent_ms=time_spent,
            )
        )
    return rows


async def analyze_game(
    session: Session,
    game: Game,
    cloud_analyzer: LichessCloudEvalAnalyzer | None = None,
    local_analyzer: Analyzer | None = None,
) -> AnalysisResult:
    """Run the analyzer for one game. Idempotent: drops + recreates Position
    rows; Mistake rows are *reconciled*, not recreated, so re-running never
    destroys user classifications (see detect_mistakes / DESIGN.md
    §"Re-analysis semantics"). Skips silently if has_evals is False (caller
    should surface).

    `cloud_analyzer` is injectable so unit tests can stub the network. None →
    real Lichess cloud-eval (production).
    `local_analyzer`, when present, fills the cloud's coverage gap during
    best-move lookups for the heuristic — typically a StockfishLocalAnalyzer
    started by the caller."""
    if not game.has_evals:
        return AnalysisResult(
            game_id=game.id,
            positions_created=0,
            mistakes_detected=0,
            skipped=True,
            reason="has_evals=False; request analysis on Lichess and re-import.",
        )

    analyzer = LichessPgnEvalAnalyzer()
    position_evals = await analyzer.analyze_game(game.pgn)
    if not position_evals:
        return AnalysisResult(
            game_id=game.id,
            positions_created=0,
            mistakes_detected=0,
            skipped=True,
            reason="PGN parse failed.",
        )

    session.execute(delete(Position).where(Position.game_id == game.id))
    rows = _to_position_rows(game, position_evals)
    session.add_all(rows)
    session.flush()  # so detect_mistakes' SELECT sees the new rows
    detection = detect_mistakes(session, game)
    session.flush()
    await assign_heuristic_suggestions(
        session, game, detection.mistakes, cloud_analyzer, local_analyzer=local_analyzer
    )
    game.analyzed_at = datetime.now(tz=timezone.utc)
    session.commit()

    return AnalysisResult(
        game_id=game.id,
        positions_created=len(rows),
        mistakes_detected=len(detection.mistakes),
        skipped=False,
        mistakes_new=detection.new,
        mistakes_updated=detection.updated,
        mistakes_removed=detection.removed,
        mistakes_preserved=detection.preserved,
    )


async def analyze_pending(
    session: Session,
    cloud_analyzer: LichessCloudEvalAnalyzer | None = None,
    local_analyzer: Analyzer | None = None,
    force: bool = False,
) -> list[AnalysisResult]:
    """Run analysis on has_evals=true games. By default only the ones not yet
    analyzed; with force=True, re-run already-analyzed games too (analyze_game
    is idempotent — positions are dropped and recreated, mistakes are
    reconciled in place so user classifications survive the re-run).

    Passes a single cloud analyzer (and single local analyzer when provided)
    to all calls so the underlying httpx client / Stockfish process is shared
    across the run."""
    stmt = select(Game).where(Game.has_evals.is_(True))
    if not force:
        stmt = stmt.where(Game.analyzed_at.is_(None))
    games = session.scalars(stmt).all()
    return [
        await analyze_game(
            session, g,
            cloud_analyzer=cloud_analyzer,
            local_analyzer=local_analyzer,
        )
        for g in games
    ]
