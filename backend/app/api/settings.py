"""Settings endpoints — read/write the AppSettings singleton row.

Lichess username stays read-only via the API: changing it implies re-seeding,
and there's no MVP UI for re-seeding. It is *exposed* on GET so the settings
page can show whose data this is. The Settings env class still owns boot-time
fields (DB path, username) — this endpoint only governs runtime-tunable
knobs."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.analyzers.stockfish_local import resolve_stockfish_path
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.models import AppSettings
from backend.app.schemas.settings import SettingsOut, SettingsUpdate
from backend.app.services.app_settings import get_app_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(row: AppSettings, settings: Settings) -> SettingsOut:
    out = SettingsOut.model_validate(row)
    # Read-only context from the env/host; not columns on the row.
    return out.model_copy(
        update={
            "lichess_username": settings.lichess_username,
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
    return _to_out(row, settings)


@router.patch("", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SettingsOut:
    row = get_app_settings(db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _to_out(row, settings)
