"""Stats endpoints — pure aggregates over Mistake/Game.

Most queries are direct GROUP BY counts; `training-prescription` ranks the
Layer A × Layer B cells by frequency and attaches text from prescription_text.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Game, Mistake
from backend.app.schemas.stats import (
    AwarenessCount,
    BreakdownItem,
    BreakdownOut,
    PrescriptionItem,
    PrescriptionOut,
    SeverityCount,
    StepCount,
    SummaryOut,
)
from backend.app.services.prescription_text import for_cell

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=SummaryOut)
def summary(db: Session = Depends(get_db)) -> SummaryOut:
    total_games = db.scalar(select(func.count()).select_from(Game)) or 0
    total_mistakes = db.scalar(select(func.count()).select_from(Mistake)) or 0

    classified = db.scalar(
        select(func.count()).select_from(Mistake).where(Mistake.classified_at.is_not(None))
    ) or 0
    unclassified = total_mistakes - classified

    suggested = db.execute(
        select(Mistake.suggested_step, func.count())
        .where(Mistake.suggested_step.is_not(None))
        .group_by(Mistake.suggested_step)
        .order_by(Mistake.suggested_step)
    ).all()
    classified_step_counts = db.execute(
        select(Mistake.classified_step, func.count())
        .where(Mistake.classified_step.is_not(None))
        .group_by(Mistake.classified_step)
        .order_by(Mistake.classified_step)
    ).all()
    awareness_counts = db.execute(
        select(Mistake.classified_awareness, func.count())
        .where(Mistake.classified_awareness.is_not(None))
        .group_by(Mistake.classified_awareness)
        .order_by(Mistake.classified_awareness)
    ).all()
    severity_counts = db.execute(
        select(Mistake.severity, func.count())
        .group_by(Mistake.severity)
        .order_by(Mistake.severity)
    ).all()

    return SummaryOut(
        total_games=total_games,
        total_mistakes=total_mistakes,
        classified=classified,
        unclassified=unclassified,
        by_suggested_step=[StepCount(step=s, count=c) for s, c in suggested],
        by_classified_step=[StepCount(step=s, count=c) for s, c in classified_step_counts],
        by_awareness=[AwarenessCount(awareness=a, count=c) for a, c in awareness_counts],
        by_severity=[SeverityCount(severity=s, count=c) for s, c in severity_counts],
    )


_ALLOWED_BREAKDOWNS = {
    "step",
    "awareness",
    "step_x_awareness",
    "phase",
    "time_pressure",
    "month",
}


def _breakdown_step(db: Session) -> list[BreakdownItem]:
    rows = db.execute(
        select(Mistake.classified_step, func.count())
        .where(Mistake.classified_step.is_not(None))
        .group_by(Mistake.classified_step)
        .order_by(Mistake.classified_step)
    ).all()
    return [BreakdownItem(label=f"step_{s}", count=c) for s, c in rows]


def _breakdown_awareness(db: Session) -> list[BreakdownItem]:
    rows = db.execute(
        select(Mistake.classified_awareness, func.count())
        .where(Mistake.classified_awareness.is_not(None))
        .group_by(Mistake.classified_awareness)
        .order_by(Mistake.classified_awareness)
    ).all()
    return [BreakdownItem(label=a, count=c) for a, c in rows]


def _breakdown_step_x_awareness(db: Session) -> list[BreakdownItem]:
    rows = db.execute(
        select(Mistake.classified_step, Mistake.classified_awareness, func.count())
        .where(
            Mistake.classified_step.is_not(None),
            Mistake.classified_awareness.is_not(None),
        )
        .group_by(Mistake.classified_step, Mistake.classified_awareness)
        .order_by(Mistake.classified_step, Mistake.classified_awareness)
    ).all()
    return [BreakdownItem(label=f"step_{s}|{a}", count=c) for s, a, c in rows]


def _breakdown_phase(db: Session) -> list[BreakdownItem]:
    """endgame_flag is a coarse but reliable phase proxy — fuller phase
    classification is post-MVP."""
    rows = db.execute(
        select(Mistake.endgame_flag, func.count())
        .group_by(Mistake.endgame_flag)
        .order_by(Mistake.endgame_flag)
    ).all()
    return [
        BreakdownItem(label="endgame" if flag else "middlegame_or_opening", count=c)
        for flag, c in rows
    ]


def _breakdown_time_pressure(db: Session) -> list[BreakdownItem]:
    rows = db.execute(
        select(Mistake.time_pressure_flag, func.count())
        .group_by(Mistake.time_pressure_flag)
        .order_by(Mistake.time_pressure_flag)
    ).all()
    return [
        BreakdownItem(label="time_pressure" if flag else "normal", count=c)
        for flag, c in rows
    ]


def _breakdown_month(db: Session) -> list[BreakdownItem]:
    """Bucket by played_at month (YYYY-MM). Mistakes whose game has no
    played_at are bucketed under 'unknown'."""
    month_label = func.strftime("%Y-%m", Game.played_at)
    rows = db.execute(
        select(month_label.label("month"), func.count(Mistake.id))
        .select_from(Mistake)
        .join(Game, Game.id == Mistake.game_id)
        .group_by("month")
        .order_by("month")
    ).all()
    return [BreakdownItem(label=label or "unknown", count=c) for label, c in rows]


_BREAKDOWN_FNS = {
    "step": _breakdown_step,
    "awareness": _breakdown_awareness,
    "step_x_awareness": _breakdown_step_x_awareness,
    "phase": _breakdown_phase,
    "time_pressure": _breakdown_time_pressure,
    "month": _breakdown_month,
}


@router.get("/breakdown", response_model=BreakdownOut)
def breakdown(
    by: str = Query(..., description=f"one of: {sorted(_ALLOWED_BREAKDOWNS)}"),
    db: Session = Depends(get_db),
) -> BreakdownOut:
    fn = _BREAKDOWN_FNS.get(by)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown breakdown {by!r}. Allowed: {sorted(_ALLOWED_BREAKDOWNS)}",
        )
    return BreakdownOut(by=by, items=fn(db))


@router.get("/training-prescription", response_model=PrescriptionOut)
def training_prescription(
    top: int = Query(default=3, ge=1, le=8),
    db: Session = Depends(get_db),
) -> PrescriptionOut:
    rows = db.execute(
        select(Mistake.classified_step, Mistake.classified_awareness, func.count().label("c"))
        .where(
            Mistake.classified_step.is_not(None),
            Mistake.classified_awareness.is_not(None),
        )
        .group_by(Mistake.classified_step, Mistake.classified_awareness)
        .order_by(desc("c"))
        .limit(top)
    ).all()

    total = db.scalar(
        select(func.count()).select_from(Mistake).where(
            Mistake.classified_step.is_not(None),
            Mistake.classified_awareness.is_not(None),
        )
    ) or 0

    items = [
        PrescriptionItem(
            step=step,
            awareness=awareness,
            count=count,
            share=(count / total) if total else 0.0,
            suggestion=for_cell(step, awareness),
        )
        for step, awareness, count in rows
    ]
    return PrescriptionOut(classified_mistakes=total, items=items)
