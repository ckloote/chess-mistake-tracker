"""Analyzer that extracts %eval and %clk annotations from a PGN.

This is the no-network MVP analyzer. python-chess understands both annotation
families natively: `node.eval()` returns a `chess.engine.PovScore` (or None),
`node.clock()` returns seconds (or None). All we do is normalize those into
`PositionEval` rows, one per ply, including ply 0 for the starting position.
"""
from __future__ import annotations

import io

import chess.pgn

from backend.app.analyzers.base import EvalResult, PositionEval


def _score_to_cp_mate(score: chess.engine.Score | None) -> tuple[int | None, int | None]:
    """Convert a python-chess Score (white-relative) into our (cp, mate_in) pair."""
    if score is None:
        return None, None
    if score.is_mate():
        return None, score.mate()
    return score.score(), None


def parse_pgn_for_positions(pgn: str) -> list[PositionEval]:
    """Walk the mainline of a PGN and emit one PositionEval per ply.

    ply 0 = starting position before any move. Each subsequent ply's eval/clock
    come from the annotations on the move that produced that position. Returns
    an empty list if the PGN can't be parsed."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []

    out: list[PositionEval] = [
        PositionEval(
            ply=0,
            fen=game.board().fen(),
            san=None,
            uci=None,
            eval_cp=None,
            mate_in=None,
            clock_ms=None,
        )
    ]

    node: chess.pgn.GameNode = game
    ply = 0
    while True:
        next_node = node.next()
        if next_node is None:
            break
        ply += 1
        board_before = node.board()
        move = next_node.move
        san = board_before.san(move) if move is not None else None
        uci = move.uci() if move is not None else None
        board_after = next_node.board()

        povscore = next_node.eval()
        eval_cp, mate_in = _score_to_cp_mate(povscore.white() if povscore else None)

        clock_seconds = next_node.clock()
        clock_ms = int(round(clock_seconds * 1000)) if clock_seconds is not None else None

        out.append(
            PositionEval(
                ply=ply,
                fen=board_after.fen(),
                san=san,
                uci=uci,
                eval_cp=eval_cp,
                mate_in=mate_in,
                clock_ms=clock_ms,
            )
        )
        node = next_node

    return out


class LichessPgnEvalAnalyzer:
    name = "lichess_pgn"

    @property
    def supports_per_position(self) -> bool:
        # We only know what the PGN already carries; arbitrary-FEN analysis
        # requires a real engine (Stockfish, planned for v1.1).
        return False

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        raise NotImplementedError(
            "LichessPgnEvalAnalyzer is PGN-bound and does not analyze loose FENs."
        )

    async def analyze_game(self, pgn: str) -> list[PositionEval]:
        return parse_pgn_for_positions(pgn)
