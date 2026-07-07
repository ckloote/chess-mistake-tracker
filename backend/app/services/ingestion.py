"""Ingestion orchestrator: pull games from a GameSource, dedupe, persist.

Also home of the per-game refresh (DESIGN.md §"Practical note on MVP
coverage"): ingest deliberately never updates an existing row, so refresh is
the path by which a game picks up changes at the source — most importantly
`%eval` annotations appearing after the user requests Lichess analysis, but
also study chapters growing moves or correcting player tags."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Game, User
from backend.app.sources.base import GameRecord, GameSource


@dataclass(frozen=True)
class IngestionResult:
    imported: int
    skipped: int
    total_in_db: int


@dataclass(frozen=True)
class RefreshResult:
    game_id: int
    pgn_changed: bool
    had_evals_before: bool
    has_evals: bool


def _record_to_game(user: User, record: GameRecord) -> Game:
    return Game(
        user_id=user.id,
        source=record.source,
        source_game_id=record.source_game_id,
        user_color=record.user_color,
        white=record.white,
        black=record.black,
        white_elo=record.white_elo,
        black_elo=record.black_elo,
        result=record.result,
        time_control=record.time_control,
        played_at=record.played_at,
        pgn=record.pgn,
        has_evals=record.has_evals,
    )


async def ingest(
    session: Session,
    user: User,
    source: GameSource,
    since: datetime | None = None,
    limit: int | None = None,
) -> IngestionResult:
    existing_ids = set(
        session.scalars(
            select(Game.source_game_id).where(
                Game.user_id == user.id, Game.source == source.name
            )
        ).all()
    )

    imported = 0
    skipped = 0
    async for record in source.fetch_recent_games(user, since=since, limit=limit):
        if record.source_game_id in existing_ids:
            skipped += 1
            continue
        session.add(_record_to_game(user, record))
        existing_ids.add(record.source_game_id)
        imported += 1

    session.commit()

    total_in_db = session.scalar(
        select(func.count(Game.id)).where(
            Game.user_id == user.id, Game.source == source.name
        )
    ) or 0

    return IngestionResult(imported=imported, skipped=skipped, total_in_db=total_in_db)


async def refresh_game(
    session: Session,
    user: User,
    source: GameSource,
    game: Game,
) -> RefreshResult | None:
    """Re-fetch `game` from its source and update the row in place.

    Metadata (players, elos, result, time control, user_color) always follows
    the fresh fetch. `analyzed_at` is cleared only when the PGN actually
    changed — that's what marks the existing Position rows stale and puts the
    game back in analyze-pending's queue; re-analysis then reconciles Mistake
    rows without touching classifications (§"Re-analysis semantics").

    Returns None when the source no longer lists the user as a player —
    nothing is modified in that case. Network/upstream errors propagate as
    httpx exceptions for the caller to map."""
    record = await source.fetch_game_by_id(user, game.source_game_id)
    if record is None:
        return None

    pgn_changed = record.pgn != game.pgn
    had_evals_before = game.has_evals

    game.pgn = record.pgn
    game.has_evals = record.has_evals
    game.user_color = record.user_color
    game.white = record.white
    game.black = record.black
    game.white_elo = record.white_elo
    game.black_elo = record.black_elo
    game.result = record.result
    game.time_control = record.time_control
    game.played_at = record.played_at
    if pgn_changed:
        game.analyzed_at = None

    session.commit()
    return RefreshResult(
        game_id=game.id,
        pgn_changed=pgn_changed,
        had_evals_before=had_evals_before,
        has_evals=game.has_evals,
    )
