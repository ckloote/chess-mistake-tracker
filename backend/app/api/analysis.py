"""Interactive position analysis: evaluate any FEN on demand via local Stockfish.

Powers the classification page's "Explore" board — the user drags pieces to
play out candidate lines and gets the engine's eval + best continuation for the
resulting position. Unlike the batch best-move cascade, this is purely local
(no cloud-eval): the user is exploring arbitrary positions that almost never
appear in the cloud's analyzed-positions cache.
"""
from __future__ import annotations

import chess
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.config import Settings, get_settings
from backend.app.schemas.analysis import (
    AnalyzedLine,
    AnalyzePositionRequest,
    PositionAnalysisOut,
)
from backend.app.services.local_engine import maybe_local_engine

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _pv_to_san(board: chess.Board, pv_uci: list[str]) -> list[str]:
    """Render a UCI principal variation as a SAN line by playing it out on a
    copy of `board`. Stops early if a move is illegal (stale/truncated PV)."""
    san_line: list[str] = []
    work = board.copy(stack=False)
    for uci in pv_uci:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in work.legal_moves:
            break
        san_line.append(work.san(move))
        work.push(move)
    return san_line


@router.post("/position", response_model=PositionAnalysisOut)
async def analyze_position(
    payload: AnalyzePositionRequest,
    settings: Settings = Depends(get_settings),
) -> PositionAnalysisOut:
    # Validate the FEN before spinning up the engine so bad input is a cheap
    # 400 rather than a wasted process launch.
    try:
        board = chess.Board(payload.fen)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid FEN: {payload.fen!r}",
        )

    async with maybe_local_engine(settings, depth=payload.depth) as engine:
        if engine is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Local Stockfish is not available. Install stockfish "
                    "(or set STOCKFISH_PATH) to use interactive analysis."
                ),
            )
        results = await engine.analyze_position(payload.fen, multipv=payload.multipv)

    lines = [
        AnalyzedLine(
            cp=r.cp,
            mate=r.mate,
            pv_uci=r.pv,
            pv_san=_pv_to_san(board, r.pv),
            depth=r.depth,
        )
        for r in results
    ]
    return PositionAnalysisOut(
        fen=payload.fen,
        turn="white" if board.turn == chess.WHITE else "black",
        lines=lines,
    )
