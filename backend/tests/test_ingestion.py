from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db import Base
from backend.app.models import Game, User
from backend.app.services.ingestion import ingest
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

    def __init__(self, records: list[GameRecord]) -> None:
        self._records = records

    async def fetch_recent_games(
        self,
        user: User,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[GameRecord]:
        for r in self._records:
            yield r

    async def fetch_game_by_id(self, game_id: str) -> GameRecord:
        raise NotImplementedError


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
