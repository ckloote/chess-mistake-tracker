"""Heuristic Layer A suggestion: tag each Mistake with one of Steps 1-4.

Implements the priority-ordered detector from DESIGN.md §"Layer A Heuristic
Suggestion": 4 → 2 → 1 → 3. Step 4 is local (uses surrounding Position rows
already in the DB). Steps 2 and 1 need the engine's preferred move from the
position before the user moved. We resolve that move local-first: a configured
Stockfish answers when present (the same engine the Explore board uses), with
Lichess cloud-eval as the fallback. Misses are silent — we fall through to
Step 3.

The best-move fetch is unconditional per mistake (not gated on Step 4): the
engine's preferred move is independently useful for the review UI's "best
move" arrow, and the result is persisted to Mistake.best_move_uci /
best_move_san so the frontend can render it without re-parsing
suggestion_debug.
"""
from __future__ import annotations

from typing import Any

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.analyzers.base import Analyzer, EvalResult
from backend.app.analyzers.lichess_cloud import LichessCloudEvalAnalyzer
from backend.app.chess_utils.winrate import MATE_CP_EQUIVALENT
from backend.app.models import Game, Mistake, Position

# Confidence values per DESIGN.md §"Layer A Heuristic Suggestion".
CONFIDENCE = {4: 0.8, 2: 0.7, 1: 0.6, 3: 0.5}

# Eval-swing threshold (in centipawns, user-view) for Step 4: opponent's reply
# must make the position at least this much worse for the user than it already was.
STEP4_CP_DROP = 200

# MultiPV used when resolving the engine's best move. This MUST match the value
# the interactive Explore board requests (frontend useAnalyzePosition, multipv:3)
# so the persisted "best move" (review-mode arrow) equals Explore's top line.
# Stockfish can rank moves differently across MultiPV settings at a fixed depth,
# so a mismatch here resurfaces the review-vs-explore inconsistency.
BEST_MOVE_MULTIPV = 3


def _user_view_cp(eval_cp: int | None, mate_in: int | None, user_color: str) -> int | None:
    """Collapse (cp, mate_in) into a single cp value from the user's view."""
    if mate_in is not None:
        cp = MATE_CP_EQUIVALENT if mate_in > 0 else -MATE_CP_EQUIVALENT
    elif eval_cp is not None:
        cp = eval_cp
    else:
        return None
    return cp if user_color == "white" else -cp


def _parse_uci(uci: str | None) -> chess.Move | None:
    if not uci:
        return None
    try:
        return chess.Move.from_uci(uci)
    except ValueError:
        return None


def _uci_to_san(fen: str, uci: str) -> str | None:
    """Best-effort SAN rendering of a UCI move from a FEN. Returns None if the
    FEN or UCI is malformed, or the move isn't legal in that position (which
    would indicate a stale cloud-eval result for a transposed line)."""
    try:
        board = chess.Board(fen)
    except ValueError:
        return None
    move = _parse_uci(uci)
    if move is None or move not in board.legal_moves:
        return None
    return board.san(move)


def _is_forcing(board: chess.Board, move: chess.Move) -> bool:
    return board.is_capture(move) or board.gives_check(move)


async def _get_best_move(
    fen: str,
    cache: dict[str, list[EvalResult]],
    cloud: LichessCloudEvalAnalyzer,
    local: Analyzer | None = None,
) -> str | None:
    """Resolve the engine's preferred move for a FEN.

    Local-first: when a local Stockfish analyzer is available it's the source of
    truth. It's higher quality than cloud-eval and, crucially, it's the same
    engine the interactive Explore board uses — so the persisted best move (the
    review-mode green arrow) agrees with what the user sees while exploring,
    rather than disagreeing because two different engines were consulted.

    Cloud-eval is the fallback: used when no local engine is configured, and as
    a last resort if local somehow returns nothing. Per-fen results are cached
    so revisited positions in the same run are free.
    """
    if fen in cache:
        results = cache[fen]
    else:
        # multipv must match the Explore board so the best move (results[0])
        # is the same line the user sees there.
        if local is not None:
            results = await local.analyze_position(fen, multipv=BEST_MOVE_MULTIPV)
            if not results or not results[0].pv:
                results = await cloud.analyze_position(fen, multipv=BEST_MOVE_MULTIPV)
        else:
            results = await cloud.analyze_position(fen, multipv=BEST_MOVE_MULTIPV)
        cache[fen] = results
    if not results or not results[0].pv:
        return None
    return results[0].pv[0]


def _step4(
    pos: Position, nxt: Position | None, user_color: str
) -> tuple[bool, dict[str, Any]]:
    """User played a move that left a forcing reply that wins material/eval.

    NOTE: DESIGN.md defines M_opp_response as "the engine's best response from
    P_after." This implementation uses the actual opponent move stored in nxt,
    not a cloud-eval lookup. The pragmatic difference: this fires when the
    opponent capitalized on the mistake, but misses cases where the opponent
    overlooked it. That's a useful signal in its own right ("you got punished
    here") and saves one cloud-eval call per mistake. A second-pass that calls
    cloud-eval on P_after when the played reply was non-forcing would catch the
    rest; deferred until we hit a real-world need for it.
    """
    if nxt is None or not nxt.uci or pos.fen is None:
        return False, {"reason": "no opponent response in DB"}
    board_after_user = chess.Board(pos.fen)
    opp_response = _parse_uci(nxt.uci)
    if opp_response is None:
        return False, {"reason": "could not parse opponent response uci"}
    forcing = _is_forcing(board_after_user, opp_response)
    if not forcing:
        return False, {"opp_response_uci": nxt.uci, "forcing": False}
    cp_after_user = _user_view_cp(pos.eval_cp, pos.mate_in, user_color)
    cp_after_opp = _user_view_cp(nxt.eval_cp, nxt.mate_in, user_color)
    if cp_after_user is None or cp_after_opp is None:
        return False, {"opp_response_uci": nxt.uci, "forcing": True, "cp_drop": None}
    cp_drop = cp_after_user - cp_after_opp
    fired = cp_drop >= STEP4_CP_DROP
    return fired, {
        "opp_response_uci": nxt.uci,
        "forcing": True,
        "cp_drop": cp_drop,
        "threshold": STEP4_CP_DROP,
    }


def _step2(
    prev: Position, pos: Position, m_best_uci: str, winrate_before: float
) -> tuple[bool, dict[str, Any]]:
    """A forcing best move existed; user played a non-forcing one in a position
    they were already at least equal in."""
    board_before = chess.Board(prev.fen)
    m_best = _parse_uci(m_best_uci)
    m_user = _parse_uci(pos.uci)
    if m_best is None or m_user is None:
        return False, {"reason": "could not parse m_best or m_user"}
    m_best_forcing = _is_forcing(board_before, m_best)
    m_user_forcing = _is_forcing(board_before, m_user)
    fired = m_best_forcing and not m_user_forcing and winrate_before >= 50.0
    return fired, {
        "m_best_uci": m_best_uci,
        "m_best_forcing": m_best_forcing,
        "m_user_forcing": m_user_forcing,
        "winrate_before": winrate_before,
    }


def _step1(
    prev: Position, pos: Position, m_best_uci: str
) -> tuple[bool, dict[str, Any]]:
    """MVP approximation: did the engine's best move respond to the piece the
    opponent just moved (capture-the-mover heuristic)? Captures the most common
    "ignored opponent's threat" pattern; will miss subtler defenses. The note
    in DESIGN.md is the canonical caveat — local Stockfish (v1.1) is the cure.

    Guard: do NOT fire when the user's own move also captured the opponent's
    mover (same destination square). In that case the user addressed the threat
    and merely recaptured with the wrong piece — a structural inaccuracy
    (falls through to Step 3), not a missed threat. Without this, every
    wrong-recapture mis-tagged as "missed opponent threat".
    """
    if not prev.uci:
        return False, {"reason": "no opponent move recorded on prev position"}
    board_before = chess.Board(prev.fen)
    m_best = _parse_uci(m_best_uci)
    m_opp = _parse_uci(prev.uci)
    m_user = _parse_uci(pos.uci)
    if m_best is None or m_opp is None:
        return False, {"reason": "could not parse m_best or m_opp"}
    best_captures_mover = (
        m_best.to_square == m_opp.to_square and board_before.is_capture(m_best)
    )
    user_captures_mover = (
        m_user is not None
        and m_user.to_square == m_opp.to_square
        and board_before.is_capture(m_user)
    )
    fired = best_captures_mover and not user_captures_mover
    return fired, {
        "m_opp_uci": prev.uci,
        "m_best_uci": m_best_uci,
        "m_best_captures_opp_mover": best_captures_mover,
        "m_user_captures_opp_mover": user_captures_mover,
    }


async def assign_heuristic_suggestions(
    session: Session,
    game: Game,
    mistakes: list[Mistake],
    cloud_analyzer: LichessCloudEvalAnalyzer | None = None,
    local_analyzer: Analyzer | None = None,
) -> None:
    """Mutates Mistake rows in place with suggested_step, suggestion_confidence,
    suggestion_debug. Does not commit — the caller (analyze_game) does.

    `local_analyzer`, when provided, fills the gap when cloud-eval returns
    nothing (most middlegame/endgame positions in non-trending games)."""
    if not mistakes:
        return

    by_ply: dict[int, Position] = {
        p.ply: p
        for p in session.scalars(
            select(Position).where(Position.game_id == game.id).order_by(Position.ply)
        ).all()
    }

    cloud = cloud_analyzer or LichessCloudEvalAnalyzer()
    cloud_cache: dict[str, list[EvalResult]] = {}

    for mistake in mistakes:
        prev = by_ply.get(mistake.ply - 1)
        pos = by_ply.get(mistake.ply)
        nxt = by_ply.get(mistake.ply + 1)
        debug: dict[str, Any] = {}

        # Fetch the engine's preferred move from P_before for every mistake
        # — needed for Steps 1/2 detection, and independently useful as the
        # green "best move" arrow in the review UI even when Step 4 fires.
        m_best_uci: str | None = None
        if prev is not None and prev.fen:
            m_best_uci = await _get_best_move(
                prev.fen, cloud_cache, cloud, local=local_analyzer
            )
            debug["m_best_uci"] = m_best_uci

        # Persist on the Mistake row when cloud returned a usable move.
        # SAN may legitimately be None (illegal/transposed/malformed) — in
        # that case we still keep the UCI so the UI can draw the arrow.
        if m_best_uci and prev is not None and prev.fen:
            mistake.best_move_uci = m_best_uci
            mistake.best_move_san = _uci_to_san(prev.fen, m_best_uci)

        suggested: int | None = None

        # Step 4 (highest priority).
        if pos is not None:
            fired, why = _step4(pos, nxt, game.user_color)
            debug["step4"] = why
            if fired:
                suggested = 4

        if suggested is None and m_best_uci and prev is not None and pos is not None:
            fired, why = _step2(prev, pos, m_best_uci, mistake.winrate_before)
            debug["step2"] = why
            if fired:
                suggested = 2

        if suggested is None and m_best_uci and prev is not None and pos is not None:
            fired, why = _step1(prev, pos, m_best_uci)
            debug["step1"] = why
            if fired:
                suggested = 1

        # Step 3 default.
        if suggested is None:
            suggested = 3
            debug["step3_default"] = True

        mistake.suggested_step = suggested
        mistake.suggestion_confidence = CONFIDENCE[suggested]
        mistake.suggestion_debug = debug
