"""Win% utilities. The cp -> winrate formula is verbatim from DESIGN.md."""
from __future__ import annotations

import math

# Mate is approximated as ±1000cp for winrate purposes. DESIGN.md notes the
# approximation doesn't matter for our use case: positions where the user is
# being mated aren't where they're "giving away an advantage."
MATE_CP_EQUIVALENT = 1000


def cp_to_winrate(cp: int) -> float:
    """Win% from white's perspective. cp is clamped to [-1000, 1000]."""
    cp = max(-1000, min(1000, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def mate_zero_white_view_cp(fen: str | None) -> int:
    """Resolve the ambiguous `mate_in == 0` ("mate is on the board") into a
    signed white-view cp value.

    A PGN `[%eval #-0]` (black delivered mate) and `[%eval #0]` both parse to
    the integer 0 — the sign doesn't survive. The FEN disambiguates: in a
    checkmate position the *side to move* is the mated side. Without a FEN we
    fall back to the historical assumption that white delivered it."""
    if fen:
        parts = fen.split()
        if len(parts) >= 2 and parts[1] == "w":
            return -MATE_CP_EQUIVALENT  # white to move ⇒ white is mated
    return MATE_CP_EQUIVALENT


def _white_winrate(
    eval_cp: int | None, mate_in: int | None, fen: str | None = None
) -> float | None:
    """Convert (cp, mate) into a white-relative winrate, or None if neither
    is set. `fen` is only consulted for mate_in == 0 (see
    mate_zero_white_view_cp)."""
    if mate_in is not None:
        # mate_in > 0 means white mates; < 0 means black mates; 0 means
        # mate has been delivered — winner derived from the FEN.
        if mate_in > 0:
            return cp_to_winrate(MATE_CP_EQUIVALENT)
        if mate_in < 0:
            return cp_to_winrate(-MATE_CP_EQUIVALENT)
        return cp_to_winrate(mate_zero_white_view_cp(fen))
    if eval_cp is not None:
        return cp_to_winrate(eval_cp)
    return None


def winrate_for_color(
    eval_cp: int | None,
    mate_in: int | None,
    user_color: str,
    fen: str | None = None,
) -> float | None:
    """Winrate from `user_color`'s perspective in [0, 100], or None if no eval.
    Pass the position's `fen` so a delivered mate (mate_in == 0) is credited
    to the right side — the int sign of "#-0" is lost in parsing."""
    white_view = _white_winrate(eval_cp, mate_in, fen)
    if white_view is None:
        return None
    if user_color == "black":
        return 100.0 - white_view
    return white_view


def winrate_drop(before: float | None, after: float | None) -> float | None:
    """before - after, or None if either side missing."""
    if before is None or after is None:
        return None
    return before - after


def severity_for_drop(
    drop: float,
    inaccuracy_threshold: float,
    mistake_threshold: float,
    blunder_threshold: float,
) -> str | None:
    """`'inaccuracy' | 'mistake' | 'blunder'` or None if drop doesn't qualify.
    Thresholds come from settings; defaults per DESIGN.md are 5/10/20."""
    if drop >= blunder_threshold:
        return "blunder"
    if drop >= mistake_threshold:
        return "mistake"
    if drop >= inaccuracy_threshold:
        return "inaccuracy"
    return None
