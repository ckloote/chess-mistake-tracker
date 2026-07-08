"""Time-control parsing and speed bucketing.

`parse_time_control` reads the PGN TimeControl header ("initial+increment",
both in seconds). `speed_of` maps that to a Lichess-style speed bucket using
estimated game duration = initial + 40 * increment. Ultrabullet is folded
into bullet — the distinction has no training value here.
"""
from __future__ import annotations

import re

_TC_RE = re.compile(r"^\s*(\d+)\s*(?:\+\s*(\d+))?\s*$")

# Valid `speed_of` outputs, in fastest-first order (drives API validation
# and the frontend select).
SPEEDS = ("bullet", "blitz", "rapid", "classical", "unknown")


def parse_time_control(tc: str | None) -> tuple[int | None, int | None]:
    """`"300+0"` -> (300, 0); a bare `"600"` (no increment recorded) ->
    (600, 0). Anything non-standard (OTB, correspondence `1/86400`, empty)
    -> (None, None) — caller treats those plies as unmeasurable."""
    if not tc:
        return None, None
    m = _TC_RE.match(tc)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2) or 0)


def speed_of(tc: str | None) -> str:
    """Speed bucket for a TimeControl string. Thresholds follow Lichess:
    <3 min estimated -> bullet, <8 min -> blitz, <25 min -> rapid, else
    classical. Unparseable (OTB studies, correspondence) -> "unknown"."""
    initial, increment = parse_time_control(tc)
    if initial is None:
        return "unknown"
    total = initial + 40 * (increment or 0)
    if total < 180:
        return "bullet"
    if total < 480:
        return "blitz"
    if total < 1500:
        return "rapid"
    return "classical"
