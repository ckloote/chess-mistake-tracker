import logging
from datetime import date

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.app.api.dates import end_of_day, start_of_day
from backend.app.api.deps import get_configured_user
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.models import Game, Mistake, Position
from backend.app.schemas.games import (
    AnalyzePendingResponse,
    AnalyzeResponse,
    GameListOut,
    GameOut,
    ImportRequest,
    ImportResponse,
    RefreshResponse,
)
from backend.app.schemas.mistakes import GameDetailOut
from backend.app.services.analysis import AnalysisResult, analyze_game, analyze_pending
from backend.app.services.app_settings import get_app_settings
from backend.app.services.ingestion import ingest, refresh_game
from backend.app.services.local_engine import maybe_local_engine
from backend.app.sources.base import RefreshUnsupported, SourceMisconfigured
from backend.app.sources.registry import get_source, known_sources

log = logging.getLogger(__name__)

router = APIRouter(prefix="/games", tags=["games"])


def _to_analyze_response(r: AnalysisResult) -> AnalyzeResponse:
    return AnalyzeResponse(
        game_id=r.game_id,
        positions_created=r.positions_created,
        mistakes_detected=r.mistakes_detected,
        skipped=r.skipped,
        reason=r.reason,
        mistakes_new=r.mistakes_new,
        mistakes_updated=r.mistakes_updated,
        mistakes_removed=r.mistakes_removed,
        mistakes_preserved=r.mistakes_preserved,
    )


@router.post("/import", response_model=ImportResponse)
async def import_games(
    payload: ImportRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ImportResponse:
    try:
        # Sources are built from the AppSettings row so PATCH /settings edits
        # (study IDs, aliases) take effect without a restart.
        source = get_source(payload.source, get_app_settings(db))
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown source {payload.source!r}. Known: {known_sources()}",
        )
    except ValueError as e:
        # Stored settings invalid for this source (e.g. a malformed study id
        # written before PATCH-time validation existed).
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    user = get_configured_user(db, settings)
    try:
        result = await ingest(db, user, source, since=payload.since, limit=payload.limit)
    except SourceMisconfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{payload.source} returned an error: {e}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach {payload.source}: {e}",
        )
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
        stmt = stmt.where(Game.played_at >= start_of_day(from_))
    if to is not None:
        stmt = stmt.where(Game.played_at <= end_of_day(to))
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


@router.post("/{game_id}/refresh", response_model=RefreshResponse)
async def refresh_one_game(
    game_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RefreshResponse:
    """Re-fetch the game from its source (DESIGN.md §"Practical note on MVP
    coverage"): after requesting Lichess analysis on a has_evals=false game,
    refresh picks up the %eval annotations and clears analyzed_at so the game
    becomes processable. Also refreshes grown/edited study chapters."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    user = get_configured_user(db, settings)
    try:
        source = get_source(game.source, get_app_settings(db))
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    try:
        result = await refresh_game(db, user, source, game)
    except RefreshUnsupported as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Game {game.source_game_id!r} was not found on {game.source}.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{game.source} returned an error: {e}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach {game.source}: {e}",
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Refreshed data no longer lists the configured user as a player; "
                "check the username / study_player_aliases settings."
            ),
        )
    return RefreshResponse(
        game_id=result.game_id,
        pgn_changed=result.pgn_changed,
        had_evals_before=result.had_evals_before,
        has_evals=result.has_evals,
    )


@router.post("/{game_id}/analyze", response_model=AnalyzeResponse)
async def analyze_one_game(
    game_id: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found.")
    async with maybe_local_engine(settings) as local:
        result = await analyze_game(db, game, local_analyzer=local)
    return _to_analyze_response(result)


@router.post("/analyze-pending", response_model=AnalyzePendingResponse)
async def analyze_pending_games(
    force: bool = Query(
        default=False,
        description=(
            "When true, re-run analysis on already-analyzed games too. "
            "Useful when the heuristic or thresholds change. Safe for "
            "classified data: mistakes are reconciled in place and user "
            "classifications are preserved (DESIGN.md §Re-analysis semantics)."
        ),
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AnalyzePendingResponse:
    async with maybe_local_engine(settings) as local:
        results = await analyze_pending(db, local_analyzer=local, force=force)
    return AnalyzePendingResponse(
        analyzed=sum(1 for r in results if not r.skipped),
        skipped=sum(1 for r in results if r.skipped),
        results=[_to_analyze_response(r) for r in results],
    )
