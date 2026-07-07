from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base
from backend.app.models import Game, User
from backend.app.services.ingestion import ingest, refresh_game
from backend.app.sources.base import GameRecord
from backend.app.sources.lichess_online import parse_pgn_stream

FIXTURE = Path(__file__).parent / "fixtures" / "lichess_two_games.pgn"


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def seeded_user(db_session: Session) -> User:
    user = User(lichess_username="configured_user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class FakeSource:
    # Matches the `record.source` value emitted by parse_pgn_stream, so dedup keys align.
    name = "lichess_online"

    def __init__(
        self,
        records: list[GameRecord],
        by_id: dict[str, GameRecord | None] | None = None,
    ) -> None:
        self._records = records
        self._by_id = by_id or {}

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[GameRecord]:
        for r in self._records:
            yield r

    async def fetch_game_by_id(self, user: User, game_id: str) -> GameRecord | None:
        return self._by_id.get(game_id)


async def test_ingest_inserts_new_games(db_session: Session, seeded_user: User) -> None:
    records = parse_pgn_stream(FIXTURE.read_text(), "configured_user")
    source = FakeSource(records)

    result = await ingest(db_session, seeded_user, source)

    assert result.imported == 2
    assert result.skipped == 0
    assert result.total_in_db == 2

    rows = db_session.scalars(select(Game).order_by(Game.source_game_id)).all()
    assert [r.source_game_id for r in rows] == ["abcd1234", "wxyz5678"]
    by_id = {r.source_game_id: r for r in rows}
    assert by_id["abcd1234"].has_evals is True
    assert by_id["abcd1234"].user_color == "black"
    assert by_id["wxyz5678"].has_evals is False
    assert by_id["wxyz5678"].user_color == "white"


async def test_ingest_is_idempotent(db_session: Session, seeded_user: User) -> None:
    records = parse_pgn_stream(FIXTURE.read_text(), "configured_user")

    first = await ingest(db_session, seeded_user, FakeSource(records))
    second = await ingest(db_session, seeded_user, FakeSource(records))

    assert first.imported == 2
    assert second.imported == 0
    assert second.skipped == 2

    count = db_session.scalar(select(func.count(Game.id)))
    assert count == 2


# ---- refresh_game -----------------------------------------------------------

def _replace(record: GameRecord, **overrides) -> GameRecord:
    from dataclasses import replace

    return replace(record, **overrides)


async def test_refresh_picks_up_evals_and_clears_analyzed_at(
    db_session: Session, seeded_user: User
) -> None:
    """The core workflow: a game ingested without evals gets Lichess analysis;
    refresh pulls the new PGN, flips has_evals, and marks the game pending."""
    records = parse_pgn_stream(FIXTURE.read_text(), "configured_user")
    no_evals = next(r for r in records if not r.has_evals)  # wxyz5678
    await ingest(db_session, seeded_user, FakeSource([no_evals]))
    game = db_session.scalar(select(Game).where(Game.source_game_id == no_evals.source_game_id))
    assert game is not None and game.has_evals is False
    game.analyzed_at = datetime(2025, 6, 1)  # pretend something analyzed it
    db_session.commit()

    updated = _replace(
        no_evals,
        pgn=no_evals.pgn.replace("1. e4", "1. e4 { [%eval 0.2] }"),
        has_evals=True,
    )
    assert updated.pgn != no_evals.pgn  # guard: the substitution actually hit
    source = FakeSource([], by_id={no_evals.source_game_id: updated})

    result = await refresh_game(db_session, seeded_user, source, game)

    assert result is not None
    assert result.pgn_changed is True
    assert result.had_evals_before is False
    assert result.has_evals is True
    db_session.refresh(game)
    assert game.has_evals is True
    assert "[%eval 0.2]" in game.pgn
    assert game.analyzed_at is None  # back in analyze-pending's queue


async def test_refresh_identical_pgn_keeps_analyzed_at(
    db_session: Session, seeded_user: User
) -> None:
    records = parse_pgn_stream(FIXTURE.read_text(), "configured_user")
    record = records[0]
    await ingest(db_session, seeded_user, FakeSource([record]))
    game = db_session.scalar(select(Game).where(Game.source_game_id == record.source_game_id))
    assert game is not None
    analyzed_at = datetime(2025, 6, 1)
    game.analyzed_at = analyzed_at
    db_session.commit()

    source = FakeSource([], by_id={record.source_game_id: record})
    result = await refresh_game(db_session, seeded_user, source, game)

    assert result is not None
    assert result.pgn_changed is False
    db_session.refresh(game)
    assert game.analyzed_at == analyzed_at  # nothing changed; no re-analysis


async def test_refresh_returns_none_and_leaves_game_untouched_when_user_absent(
    db_session: Session, seeded_user: User
) -> None:
    records = parse_pgn_stream(FIXTURE.read_text(), "configured_user")
    record = records[0]
    await ingest(db_session, seeded_user, FakeSource([record]))
    game = db_session.scalar(select(Game).where(Game.source_game_id == record.source_game_id))
    assert game is not None
    pgn_before = game.pgn

    source = FakeSource([], by_id={})  # fetch_game_by_id -> None
    result = await refresh_game(db_session, seeded_user, source, game)

    assert result is None
    db_session.refresh(game)
    assert game.pgn == pgn_before
