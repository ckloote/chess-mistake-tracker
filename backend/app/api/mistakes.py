from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Mistake
from backend.app.schemas.mistakes import MistakeOut

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


@router.get("", response_model=list[MistakeOut])
def list_mistakes(
    game_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Mistake]:
    """Stub list endpoint for Phase 5: filter by game_id only. Phase 7 expands
    the filter set (severity, classified, time_pressure, etc.)."""
    stmt = select(Mistake).order_by(Mistake.game_id, Mistake.ply)
    if game_id is not None:
        stmt = stmt.where(Mistake.game_id == game_id)
    return list(db.scalars(stmt).all())
