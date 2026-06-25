"""Static Exchange Evaluation (SEE).

SEE answers one question about a single square: *if I initiate a capture on it
and both sides keep recapturing there with their cheapest available attacker,
what is the net material I come out ahead (or behind), in centipawns?*

It is "static" because it never calls the engine — it plays out the forced
capture sequence on one square using fixed piece values. That makes it fast and
deterministic, which is exactly what the Step-2 material-threat detector needs:
after the engine names the user's best reply in a probe position, SEE decides
whether that reply actually *wins material* (a real threat) or merely trades
evenly (not a threat). See `services/heuristics.py` and DESIGN.md
§"Step 2 — missed forcing move".

Caveat (standard for SEE): pins and check-legality are ignored. The swap assumes
every attacker of the square may legally recapture, so in pin-heavy positions the
value can be off. This is the textbook speed/accuracy trade-off and is acceptable
for a coarse "is this a winning capture?" gate. X-rays (a rook/bishop/queen
behind another slider on the same line) *are* handled, because the swap mutates a
board copy and re-derives attackers after each piece leaves the square.
"""
from __future__ import annotations

import chess

# Centipawn piece values used for the exchange. The king is given a large
# sentinel value so it is only ever used as the attacker of last resort (you
# never "win" by being the side that must recapture with the king into more
# attackers — the swap's stop-loss handles that).
PIECE_VALUES: dict[chess.PieceType, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000,
}


def _least_valuable_attacker(
    board: chess.Board, square: int, color: chess.Color
) -> tuple[int, chess.PieceType] | None:
    """Cheapest piece of `color` currently attacking `square`, as
    (from_square, piece_type), or None. Attackers are recomputed against
    `board`'s live occupancy, so removing a front piece exposes any x-ray
    behind it on the next call."""
    for piece_type in (
        chess.PAWN,
        chess.KNIGHT,
        chess.BISHOP,
        chess.ROOK,
        chess.QUEEN,
        chess.KING,
    ):
        mask = board.attackers_mask(color, square) & board.pieces_mask(
            piece_type, color
        )
        if mask:
            return chess.lsb(mask), piece_type
    return None


def static_exchange_eval(board: chess.Board, move: chess.Move) -> int:
    """Net centipawn material won by the side to move if it plays the capture
    `move` and the exchange on `move.to_square` is played out optimally.

    Positive means the capture wins material; <= 0 means it loses or merely
    trades. `move` must be a capture (including en passant); a non-capture
    returns 0.
    """
    target = move.to_square

    if board.is_en_passant(move):
        captured_value = PIECE_VALUES[chess.PAWN]
    else:
        captured = board.piece_at(target)
        if captured is None:
            return 0  # not a capture
        captured_value = PIECE_VALUES[captured.piece_type]

    mover = board.piece_at(move.from_square)
    if mover is None:  # malformed move; nothing to evaluate
        return 0

    # Replay the exchange on a mutable copy so attacker lookups see x-rays.
    work = board.copy(stack=False)
    work.remove_piece_at(move.from_square)
    if board.is_en_passant(move):
        captured_pawn_sq = target + (-8 if board.turn == chess.WHITE else 8)
        work.remove_piece_at(captured_pawn_sq)
    work.set_piece_at(target, mover)

    # gains[i] is the material balance (from the original mover's view) of the
    # piece standing on `target` being captured at depth i, before pruning.
    gains = [captured_value]
    value_on_target = PIECE_VALUES[mover.piece_type]
    side_to_recapture = not board.turn

    while True:
        attacker = _least_valuable_attacker(work, target, side_to_recapture)
        if attacker is None:
            break
        from_sq, piece_type = attacker
        # Whoever recaptures wins the piece currently on the square, net of the
        # best the opponent could already secure (gains[-1]).
        gains.append(value_on_target - gains[-1])
        piece = work.piece_at(from_sq)
        work.remove_piece_at(from_sq)
        work.set_piece_at(target, piece)
        value_on_target = PIECE_VALUES[piece_type]
        side_to_recapture = not side_to_recapture

    # Negamax the swap list back to the root: at each depth the side to move may
    # decline to recapture if continuing would lose material (stop-loss).
    for i in range(len(gains) - 1, 0, -1):
        gains[i - 1] = -max(-gains[i - 1], gains[i])
    return gains[0]
