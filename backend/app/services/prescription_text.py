"""Bucket-specific advice strings shown in the training-prescription UI.

Keyed by (Layer A step, Layer B awareness). Stable text — the analytics layer
ranks cells; this file just maps a cell to its prescription. Wording mirrors
the source article's framing so the user recognizes the pattern."""
from __future__ import annotations

# Layer A: 1 = missed opponent's threat; 2 = missed forcing move;
#          3 = strategic inaccuracy; 4 = failed blunder check.
# Layer B: "got_it_wrong" (you saw it, evaluated it wrong) vs
#          "didnt_see_it"  (you didn't see it at all).

PRESCRIPTIONS: dict[tuple[int, str], str] = {
    (1, "got_it_wrong"): (
        "You saw the opponent's threat but misjudged it. Drill calculation depth "
        "on forcing replies — when you spot a threat, calculate one move further "
        "than feels necessary."
    ),
    (1, "didnt_see_it"): (
        "You didn't notice the opponent's threat. Add 'what changed on their last "
        "move' as a non-negotiable step before choosing your reply."
    ),
    (2, "got_it_wrong"): (
        "You considered the forcing move and rejected it for the wrong reason. "
        "Tactics puzzles emphasizing quiet alternatives vs. forcing lines will "
        "recalibrate which evaluation deserves more trust."
    ),
    (2, "didnt_see_it"): (
        "You didn't see the forcing move at all. Build the habit of scanning every "
        "check, capture, and threat for both sides on every move."
    ),
    (3, "got_it_wrong"): (
        "Strategic misjudgement — the position called for a plan you evaluated "
        "incorrectly. Annotate similar positions from master games to recalibrate."
    ),
    (3, "didnt_see_it"): (
        "Strategic blind spot — the right idea wasn't even on your radar. Studying "
        "annotated games in the same structure surfaces the menu of common plans."
    ),
    (4, "got_it_wrong"): (
        "Blunder-check executed but flawed. When you check 'their best forcing "
        "reply,' calculate it to the end of the line rather than stopping at the "
        "first move."
    ),
    (4, "didnt_see_it"): (
        "Skipped the blunder check entirely. Before pressing the clock, ask "
        "'what's their best forcing reply?' — make this physical, every move."
    ),
}


def for_cell(step: int, awareness: str) -> str:
    return PRESCRIPTIONS.get(
        (step, awareness),
        "Pattern noted — keep classifying mistakes to refine the prescription.",
    )
