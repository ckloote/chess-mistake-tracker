"""Ingestion orchestrator: pull games from a GameSource, dedupe, persist."""
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
