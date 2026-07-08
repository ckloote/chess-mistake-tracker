"""Stats endpoints — pure aggregates over Mistake/Game.

Most queries are direct GROUP BY counts; `training-prescription` ranks the
Layer A × Layer B cells by frequency and attaches text from prescription_text.

All three endpoints accept the same optional filters (`StatFilters`): date
range, source, user color, severity, and speed bucket. Every aggregate joins
Game (the FK makes the inner join lossless) so game-level predicates apply
uniformly. Speed can't be expressed in SQL — it's derived from the
TimeControl string — so that one filter resolves to a game-id list in Python
first; fine at personal-database scale.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import ColumnElement, desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.dates import end_of_day, start_of_day
from backend.app.chess_utils.time_control import SPEEDS, speed_of
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

_SPEED_PATTERN = "^(" + "|".join(SPEEDS) + ")$"


@dataclass(frozen=True)
class StatFilters:
    from_: date | None = None
    to: date | None = None
    source: str | None = None
    color: str | None = None
    severity: str | None = None
    speed: str | None = None

    def game_conditions(self, db: Session) -> list[ColumnElement[bool]]:
        """Predicates on Game columns — everything except severity."""
        conds: list[ColumnElement[bool]] = []
        if self.from_ is not None:
            conds.append(Game.played_at >= start_of_day(self.from_))
        if self.to is not None:
            conds.append(Game.played_at <= end_of_day(self.to))
        if self.source is not None:
            conds.append(Game.source == self.source)
        if self.color is not None:
            conds.append(Game.user_color == self.color)
        if self.speed is not None:
            rows = db.execute(select(Game.id, Game.time_control)).all()
            ids = [gid for gid, tc in rows if speed_of(tc) == self.speed]
            conds.append(Game.id.in_(ids))
        return conds

    def mistake_conditions(self, db: Session) -> list[ColumnElement[bool]]:
        """Game predicates plus severity — for queries joined Mistake↔Game."""
        conds = self.game_conditions(db)
        if self.severity is not None:
            conds.append(Mistake.severity == self.severity)
        return conds


def stat_filters(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    source: str | None = Query(default=None, description="e.g. lichess_online, lichess_study"),
    color: str | None = Query(default=None, pattern="^(white|black)$"),
    severity: str | None = Query(default=None, pattern="^(inaccuracy|mistake|blunder)$"),
    speed: str | None = Query(default=None, pattern=_SPEED_PATTERN),
) -> StatFilters:
    return StatFilters(
        from_=from_, to=to, source=source, color=color, severity=severity, speed=speed
    )


def _mistake_stmt(base, filters: StatFilters, db: Session):
    return base.join(Game, Game.id == Mistake.game_id).where(
        *filters.mistake_conditions(db)
    )


@router.get("/summary", response_model=SummaryOut)
def summary(
    filters: StatFilters = Depends(stat_filters),
    db: Session = Depends(get_db),
) -> SummaryOut:
    total_games = db.scalar(
        select(func.count()).select_from(Game).where(*filters.game_conditions(db))
    ) or 0
    total_mistakes = db.scalar(
        _mistake_stmt(select(func.count()).select_from(Mistake), filters, db)
    ) or 0

    classified = db.scalar(
        _mistake_stmt(select(func.count()).select_from(Mistake), filters, db).where(
            Mistake.classified_at.is_not(None)
        )
    ) or 0
    unclassified = total_mistakes - classified

    suggested = db.execute(
        _mistake_stmt(select(Mistake.suggested_step, func.count()), filters, db)
        .where(Mistake.suggested_step.is_not(None))
        .group_by(Mistake.suggested_step)
        .order_by(Mistake.suggested_step)
    ).all()
    classified_step_counts = db.execute(
        _mistake_stmt(select(Mistake.classified_step, func.count()), filters, db)
        .where(Mistake.classified_step.is_not(None))
        .group_by(Mistake.classified_step)
        .order_by(Mistake.classified_step)
    ).all()
    awareness_counts = db.execute(
        _mistake_stmt(select(Mistake.classified_awareness, func.count()), filters, db)
        .where(Mistake.classified_awareness.is_not(None))
        .group_by(Mistake.classified_awareness)
        .order_by(Mistake.classified_awareness)
    ).all()
    severity_counts = db.execute(
        _mistake_stmt(select(Mistake.severity, func.count()), filters, db)
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


def _breakdown_step(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    rows = db.execute(
        _mistake_stmt(select(Mistake.classified_step, func.count()), filters, db)
        .where(Mistake.classified_step.is_not(None))
        .group_by(Mistake.classified_step)
        .order_by(Mistake.classified_step)
    ).all()
    return [BreakdownItem(label=f"step_{s}", count=c) for s, c in rows]


def _breakdown_awareness(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    rows = db.execute(
        _mistake_stmt(select(Mistake.classified_awareness, func.count()), filters, db)
        .where(Mistake.classified_awareness.is_not(None))
        .group_by(Mistake.classified_awareness)
        .order_by(Mistake.classified_awareness)
    ).all()
    return [BreakdownItem(label=a, count=c) for a, c in rows]


def _breakdown_step_x_awareness(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    rows = db.execute(
        _mistake_stmt(
            select(Mistake.classified_step, Mistake.classified_awareness, func.count()),
            filters,
            db,
        )
        .where(
            Mistake.classified_step.is_not(None),
            Mistake.classified_awareness.is_not(None),
        )
        .group_by(Mistake.classified_step, Mistake.classified_awareness)
        .order_by(Mistake.classified_step, Mistake.classified_awareness)
    ).all()
    return [BreakdownItem(label=f"step_{s}|{a}", count=c) for s, a, c in rows]


def _breakdown_phase(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    """endgame_flag is a coarse but reliable phase proxy — fuller phase
    classification is post-MVP."""
    rows = db.execute(
        _mistake_stmt(select(Mistake.endgame_flag, func.count()), filters, db)
        .group_by(Mistake.endgame_flag)
        .order_by(Mistake.endgame_flag)
    ).all()
    return [
        BreakdownItem(label="endgame" if flag else "middlegame_or_opening", count=c)
        for flag, c in rows
    ]


def _breakdown_time_pressure(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    rows = db.execute(
        _mistake_stmt(select(Mistake.time_pressure_flag, func.count()), filters, db)
        .group_by(Mistake.time_pressure_flag)
        .order_by(Mistake.time_pressure_flag)
    ).all()
    return [
        BreakdownItem(label="time_pressure" if flag else "normal", count=c)
        for flag, c in rows
    ]


def _breakdown_month(db: Session, filters: StatFilters) -> list[BreakdownItem]:
    """Bucket by played_at month (YYYY-MM). Mistakes whose game has no
    played_at are bucketed under 'unknown'."""
    month_label = func.strftime("%Y-%m", Game.played_at)
    rows = db.execute(
        _mistake_stmt(
            select(month_label.label("month"), func.count(Mistake.id)).select_from(Mistake),
            filters,
            db,
        )
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
    filters: StatFilters = Depends(stat_filters),
    db: Session = Depends(get_db),
) -> BreakdownOut:
    fn = _BREAKDOWN_FNS.get(by)
    if fn is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown breakdown {by!r}. Allowed: {sorted(_ALLOWED_BREAKDOWNS)}",
        )
    return BreakdownOut(by=by, items=fn(db, filters))


@router.get("/training-prescription", response_model=PrescriptionOut)
def training_prescription(
    top: int = Query(default=3, ge=1, le=8),
    filters: StatFilters = Depends(stat_filters),
    db: Session = Depends(get_db),
) -> PrescriptionOut:
    rows = db.execute(
        _mistake_stmt(
            select(Mistake.classified_step, Mistake.classified_awareness, func.count().label("c")),
            filters,
            db,
        )
        .where(
            Mistake.classified_step.is_not(None),
            Mistake.classified_awareness.is_not(None),
        )
        .group_by(Mistake.classified_step, Mistake.classified_awareness)
        .order_by(desc("c"))
        .limit(top)
    ).all()

    total = db.scalar(
        _mistake_stmt(select(func.count()).select_from(Mistake), filters, db).where(
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
