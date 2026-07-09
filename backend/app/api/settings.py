"""Settings endpoints — read/write the AppSettings singleton row.

Lichess username stays read-only via the API: changing it implies re-seeding,
and there's no MVP UI for re-seeding. It is *exposed* on GET so the settings
page can show whose data this is. The chess.com username, by contrast, is
editable — it lives on the User row and only drives the chesscom import. The
Settings env class still owns boot-time fields (DB path, Lichess username) —
this endpoint governs runtime-tunable knobs."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.analyzers.stockfish_local import resolve_stockfish_path
from backend.app.api.deps import get_configured_user
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.models import AppSettings, User
from backend.app.schemas.settings import SettingsOut, SettingsUpdate
from backend.app.services.app_settings import get_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(row: AppSettings, settings: Settings, db: Session) -> SettingsOut:
    out = SettingsOut.model_validate(row)
    # The user row may not exist yet (pre-seed) — the page must still load.
    user = db.scalar(select(User).where(User.lichess_username == settings.lichess_username))
    # Read-only context from the env/host; not columns on the row.
    return out.model_copy(
        update={
            "lichess_username": settings.lichess_username,
            "chesscom_username": user.chesscom_username if user else None,
            "stockfish_available": resolve_stockfish_path(settings.stockfish_path or None)
            is not None,
        }
    )


@router.get("", response_model=SettingsOut)
def read_settings(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SettingsOut:
    row = get_app_settings(db)
    # If get_app_settings bootstrapped a new row it was only flushed; commit
    # here so the row persists across requests.
    db.commit()
    return _to_out(row, settings, db)


@router.patch("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SettingsOut:
    row = get_app_settings(db)
    data = payload.model_dump(exclude_unset=True)
    if "chesscom_username" in data:
        # Not an AppSettings column — it lives on the User row.
        user = get_configured_user(db, settings)
        user.chesscom_username = data.pop("chesscom_username")
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _to_out(row, settings, db)
