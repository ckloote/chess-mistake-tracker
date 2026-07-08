"""Date-boundary helpers shared by list/stats filter params.

Query params give whole days; games store tz-aware timestamps — an inclusive
[from, to] day range needs the day's first and last instants.
"""
from datetime import date, datetime, time, timezone


def start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=timezone.utc)
