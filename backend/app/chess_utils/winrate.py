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


def _white_winrate(eval_cp: int | None, mate_in: int | None) -> float | None:
    """Convert (cp, mate) into a white-relative winrate, or None if neither
    is set."""
    if mate_in is not None:
        # mate_in > 0 means white mates; < 0 means black mates; 0 means
        # the side to move is mated (game over). Either way, treat as fully
        # decisive in the appropriate direction.
        if mate_in > 0:
            return cp_to_winrate(MATE_CP_EQUIVALENT)
        if mate_in < 0:
            return cp_to_winrate(-MATE_CP_EQUIVALENT)
        return cp_to_winrate(MATE_CP_EQUIVALENT)  # mate_in == 0: just delivered
    if eval_cp is not None:
        return cp_to_winrate(eval_cp)
    return None


def winrate_for_color(
    eval_cp: int | None, mate_in: int | None, user_color: str
) -> float | None:
    """Winrate from `user_color`'s perspective in [0, 100], or None if no eval."""
    white_view = _white_winrate(eval_cp, mate_in)
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
