from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.models import Game, User
from backend.app.schemas.games import GameOut, ImportRequest, ImportResponse
from backend.app.services.ingestion import ingest
from backend.app.sources.registry import get_source, known_sources

router = APIRouter(prefix="/games", tags=["games"])


def _get_configured_user(db: Session, settings: Settings) -> User:
    if not settings.lichess_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LICHESS_USERNAME is not configured.",
        )
    user = db.scalar(select(User).where(User.lichess_username == settings.lichess_username))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configured user not found in DB. Run `make seed` first.",
        )
    return user


@router.post("/import", response_model=ImportResponse)
async def import_games(
    payload: ImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportResponse:
    try:
        source = get_source(payload.source)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source {payload.source!r}. Known: {known_sources()}",
        )

    user = _get_configured_user(db, settings)
    result = await ingest(db, user, source, since=payload.since, limit=payload.limit)
    return ImportResponse(
        source=payload.source,
        imported=result.imported,
        skipped=result.skipped,
        total_in_db=result.total_in_db,
    )


@router.get("", response_model=list[GameOut])
def list_games(
    source: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Game]:
    stmt = select(Game).order_by(Game.played_at.desc().nulls_last(), Game.ingested_at.desc())
    if source is not None:
        stmt = stmt.where(Game.source == source)
    return list(db.scalars(stmt).all())
