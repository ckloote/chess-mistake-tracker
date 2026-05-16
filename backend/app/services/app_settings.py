"""Helpers around the AppSettings singleton row.

The row is created on first read using config.Settings defaults. After that the
DB is the source of truth — the API's PATCH /settings writes here, and mistake
detection reads from here. Boot-time fields (DB path, Lichess username) stay
in config.Settings since they're needed before a DB session exists."""
from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.models import AppSettings

SINGLETON_ID = 1


def _make_default(s: Settings) -> AppSettings:
    return AppSettings(
        id=SINGLETON_ID,
        winrate_inaccuracy=s.winrate_inaccuracy,
        winrate_mistake=s.winrate_mistake,
        winrate_blunder=s.winrate_blunder,
        suppress_below=s.suppress_below,
        suppress_above_before=s.suppress_above_before,
        suppress_above_after=s.suppress_above_after,
        lichess_study_ids=list(s.lichess_study_ids),
        study_player_aliases=list(s.study_player_aliases),
    )


def get_app_settings(session: Session) -> AppSettings:
    """Return the singleton row, creating it from env defaults if absent.
    The bootstrap insert is only flushed — the caller is responsible for
    committing. Read-only callers (e.g. detect_mistakes inside analyze_game)
    get the row visible to their session; the surrounding transaction's
    commit finalizes the bootstrap, and a rollback simply re-creates it."""
    row = session.get(AppSettings, SINGLETON_ID)
    if row is None:
        row = _make_default(get_settings())
        session.add(row)
        session.flush()
    return row
