"""Position-phase heuristics: endgame detection, transition detection."""
from __future__ import annotations

import chess

# Standard piece values, kings/pawns excluded.
_PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.QUEEN: 9,
    chess.ROOK: 5,
    chess.BISHOP: 3,
    chess.KNIGHT: 3,
}

# Endgame threshold: total non-pawn material across both sides ≤ this value.
# Starting position has 62 (2*9 + 4*5 + 4*3 + 4*3). Queens-off middlegame ≈ 44.
# 24 captures positions like queen-and-minor each side, R+N each side, etc.
ENDGAME_MATERIAL_THRESHOLD = 24


def _non_pawn_material(board: chess.Board) -> int:
    total = 0
    for piece_type, value in _PIECE_VALUES.items():
        total += value * (
            len(board.pieces(piece_type, chess.WHITE))
            + len(board.pieces(piece_type, chess.BLACK))
        )
    return total


def is_endgame(board: chess.Board) -> bool:
    return _non_pawn_material(board) <= ENDGAME_MATERIAL_THRESHOLD


def queens_off(board: chess.Board) -> bool:
    return not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(
        chess.QUEEN, chess.BLACK
    )


def detected_transition(board_before: chess.Board, board_after: chess.Board) -> bool:
    """Did this move materially change the character of the position?

    MVP definition: queens just came off OR a piece worth ≥ 5 (rook/queen) was
    captured. Pawn-structure-change detection is post-MVP.
    """
    # Queens-off transition.
    if not queens_off(board_before) and queens_off(board_after):
        return True
    # Major capture: rook or queen disappeared from either side.
    for piece_type in (chess.QUEEN, chess.ROOK):
        before_count = len(board_before.pieces(piece_type, chess.WHITE)) + len(
            board_before.pieces(piece_type, chess.BLACK)
        )
        after_count = len(board_after.pieces(piece_type, chess.WHITE)) + len(
            board_after.pieces(piece_type, chess.BLACK)
        )
        if after_count < before_count:
            return True
    return False


def is_quiet_position(board: chess.Board) -> bool:
    """No checks or captures available for the side to move. Used by the Phase 6
    heuristic; included here so chess_utils stays the home of position predicates."""
    if board.is_check():
        return False
    for move in board.legal_moves:
        if board.is_capture(move) or board.gives_check(move):
            return False
    return True
