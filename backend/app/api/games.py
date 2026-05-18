from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.models import Game, Mistake, Position, User
from backend.app.schemas.games import (
    AnalyzePendingResponse,
    AnalyzeResponse,
    GameListOut,
    GameOut,
    ImportRequest,
    ImportResponse,
)
from backend.app.schemas.mistakes import GameDetailOut
from backend.app.services.analysis import analyze_game, analyze_pending
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


def _start_of_day(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max, tzinfo=timezone.utc)


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


@router.get("", response_model=GameListOut)
def list_games(
    source: str | None = Query(default=None),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    result: str | None = Query(default=None, description="e.g. 1-0, 0-1, 1/2-1/2, *"),
    color: str | None = Query(default=None, pattern="^(white|black)$"),
    analyzed_only: bool = Query(default=False),
    has_mistakes: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> GameListOut:
    stmt = select(Game)
    if source is not None:
        stmt = stmt.where(Game.source == source)
    if from_ is not None:
        stmt = stmt.where(Game.played_at >= _start_of_day(from_))
    if to is not None:
        stmt = stmt.where(Game.played_at <= _end_of_day(to))
    if result is not None:
        stmt = stmt.where(Game.result == result)
    if color is not None:
        stmt = stmt.where(Game.user_color == color)
    if analyzed_only:
        stmt = stmt.where(Game.analyzed_at.is_not(None))
    if has_mistakes is True:
        stmt = stmt.where(exists().where(Mistake.game_id == Game.id))
    elif has_mistakes is False:
        stmt = stmt.where(~exists().where(Mistake.game_id == Game.id))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    stmt = (
        stmt.order_by(Game.played_at.desc().nulls_last(), Game.ingested_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt).all())
    return GameListOut(
        total=total,
        page=page,
        page_size=page_size,
        items=[GameOut.model_validate(g) for g in items],
    )


@router.get("/{game_id}", response_model=GameDetailOut)
def get_game(game_id: int, db: Session = Depends(get_db)) -> GameDetailOut:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")

    positions = list(
        db.scalars(
            select(Position).where(Position.game_id == game.id).order_by(Position.ply)
        ).all()
    )
    mistakes = list(
        db.scalars(
            select(Mistake).where(Mistake.game_id == game.id).order_by(Mistake.ply)
        ).all()
    )
    return GameDetailOut.model_validate(
        {
            **GameOut.model_validate(game).model_dump(),
            "pgn": game.pgn,
            "positions": positions,
            "mistakes": mistakes,
        }
    )


@router.post("/{game_id}/analyze", response_model=AnalyzeResponse)
async def analyze_one_game(
    game_id: int,
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    result = await analyze_game(db, game)
    return AnalyzeResponse(
        game_id=result.game_id,
        positions_created=result.positions_created,
        mistakes_detected=result.mistakes_detected,
        skipped=result.skipped,
        reason=result.reason,
    )


@router.post("/analyze-pending", response_model=AnalyzePendingResponse)
async def analyze_pending_games(
    force: bool = Query(
        default=False,
        description=(
            "When true, re-run analysis on already-analyzed games too. "
            "Useful when the heuristic or thresholds change and the existing "
            "Mistake/Position rows need backfilling."
        ),
    ),
    db: Session = Depends(get_db),
) -> AnalyzePendingResponse:
    results = await analyze_pending(db, force=force)
    return AnalyzePendingResponse(
        analyzed=sum(1 for r in results if not r.skipped),
        skipped=sum(1 for r in results if r.skipped),
        results=[
            AnalyzeResponse(
                game_id=r.game_id,
                positions_created=r.positions_created,
                mistakes_detected=r.mistakes_detected,
                skipped=r.skipped,
                reason=r.reason,
            )
            for r in results
        ],
    )
