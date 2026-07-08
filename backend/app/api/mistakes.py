from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.dates import end_of_day, start_of_day
from backend.app.db import get_db
from backend.app.models import Game, Mistake, Position
from backend.app.schemas.games import GameOut, PositionOut
from backend.app.schemas.mistakes import (
    MistakeDetailOut,
    MistakeListOut,
    MistakeOut,
    MistakeUpdate,
)

router = APIRouter(prefix="/mistakes", tags=["mistakes"])


@router.get("", response_model=MistakeListOut)
def list_mistakes(
    game_id: int | None = Query(default=None),
    step: int | None = Query(default=None, ge=1, le=4, description="filter by classified_step"),
    awareness: str | None = Query(default=None, pattern="^(got_it_wrong|didnt_see_it)$"),
    severity: str | None = Query(default=None, pattern="^(inaccuracy|mistake|blunder)$"),
    time_pressure: bool | None = Query(default=None),
    unclassified_only: bool = Query(default=False),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> MistakeListOut:
    stmt = select(Mistake).join(Game, Game.id == Mistake.game_id)
    if game_id is not None:
        stmt = stmt.where(Mistake.game_id == game_id)
    if step is not None:
        stmt = stmt.where(Mistake.classified_step == step)
    if awareness is not None:
        stmt = stmt.where(Mistake.classified_awareness == awareness)
    if severity is not None:
        stmt = stmt.where(Mistake.severity == severity)
    if time_pressure is not None:
        stmt = stmt.where(Mistake.time_pressure_flag.is_(time_pressure))
    if unclassified_only:
        stmt = stmt.where(Mistake.classified_at.is_(None))
    if from_ is not None:
        stmt = stmt.where(Game.played_at >= start_of_day(from_))
    if to is not None:
        stmt = stmt.where(Game.played_at <= end_of_day(to))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    stmt = (
        stmt.order_by(
            Game.played_at.desc().nulls_last(),
            Mistake.game_id,
            Mistake.ply,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt).all())
    return MistakeListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[MistakeOut.model_validate(m) for m in items],
    )


@router.get("/{mistake_id}", response_model=MistakeDetailOut)
def get_mistake(mistake_id: int, db: Session = Depends(get_db)) -> MistakeDetailOut:
    mistake = db.get(Mistake, mistake_id)
    if mistake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mistake not found.")

    game = db.get(Game, mistake.game_id)
    assert game is not None  # FK guarantees this

    positions = {
        p.ply: p
        for p in db.scalars(
            select(Position).where(
                Position.game_id == mistake.game_id,
                Position.ply.in_([mistake.ply - 1, mistake.ply, mistake.ply + 1]),
            )
        ).all()
    }
    return MistakeDetailOut.model_validate(
        {
            **MistakeOut.model_validate(mistake).model_dump(),
            "game": GameOut.model_validate(game),
            "position_before": (
                PositionOut.model_validate(positions[mistake.ply - 1])
                if mistake.ply - 1 in positions
                else None
            ),
            "position_at_move": (
                PositionOut.model_validate(positions[mistake.ply])
                if mistake.ply in positions
                else None
            ),
            "position_after_response": (
                PositionOut.model_validate(positions[mistake.ply + 1])
                if mistake.ply + 1 in positions
                else None
            ),
        }
    )


@router.patch("/{mistake_id}", response_model=MistakeOut)
def update_mistake(
    mistake_id: int,
    payload: MistakeUpdate,
    db: Session = Depends(get_db),
) -> MistakeOut:
    mistake = db.get(Mistake, mistake_id)
    if mistake is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mistake not found.")

    fields = payload.model_dump(exclude_unset=True)
    classification_touched = any(
        k in fields for k in ("classified_step", "classified_awareness")
    )

    for key, value in fields.items():
        setattr(mistake, key, value)

    # Stamp classified_at the first time either classification field is set,
    # and refresh it on subsequent changes — the UI's notion of "when did I
    # classify this" should reflect the latest decision. Clearing BOTH fields
    # un-classifies the mistake: classified_at resets too, so the row returns
    # to the unclassified queue instead of lingering half-classified.
    if classification_touched:
        if mistake.classified_step is None and mistake.classified_awareness is None:
            mistake.classified_at = None
        else:
            mistake.classified_at = datetime.now(tz=timezone.utc)

    db.commit()
    db.refresh(mistake)
    return MistakeOut.model_validate(mistake)
