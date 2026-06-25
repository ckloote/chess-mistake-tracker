"""Unit tests for Static Exchange Evaluation (chess_utils/see.py).

Each FEN is hand-built so the exchange on the target square has a known
material outcome, independent of any engine."""
from __future__ import annotations

import chess

from backend.app.chess_utils.see import static_exchange_eval


def _see(fen: str, uci: str) -> int:
    board = chess.Board(fen)
    return static_exchange_eval(board, chess.Move.from_uci(uci))


def test_clean_capture_of_undefended_pawn() -> None:
    # White Rd2 takes an undefended black pawn on d5. Nothing recaptures.
    assert _see("4k3/8/8/3p4/8/8/3R4/4K3 w - - 0 1", "d2d5") == 100


def test_losing_capture_queen_takes_defended_pawn() -> None:
    # White queen grabs b5 (a pawn) but a6 recaptures the queen: 100 - 900.
    assert _see("4k3/8/p7/1p6/8/3Q4/8/4K3 w - - 0 1", "d3b5") == -800


def test_even_trade_knight_for_defended_knight() -> None:
    # Nc3xd5 wins a knight (320) but e6 pawn recaptures the knight (320): net 0.
    assert _see("4k3/8/4p3/3n4/8/2N5/8/4K3 w - - 0 1", "c3d5") == 0


def test_xray_battery_recaptures_after_front_piece_leaves() -> None:
    # Doubled rooks d2/d1 vs a single defending rook d8 over a pawn on d5.
    # Rd2xd5, Rd8xd5, Rd1xd5 — the back rook only attacks d5 once the front one
    # has left, which SEE must account for. Net: +pawn +rook -rook = +100.
    assert _see("3rk3/8/8/3p4/8/8/3R4/3RK3 w - - 0 1", "d2d5") == 100


def test_en_passant_capture() -> None:
    # e5 takes d-pawn en passant; the captured pawn is undefended.
    assert _see("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6") == 100


def test_non_capture_is_zero() -> None:
    assert static_exchange_eval(chess.Board(), chess.Move.from_uci("e2e4")) == 0
