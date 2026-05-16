"""Shared fixtures for API tests.

Each test gets a fresh in-memory SQLite with all tables created. The FastAPI
app's `get_db` dependency is overridden to hand out sessions bound to that
DB, so endpoints operate against the test DB rather than the real one in
./data/chess.db.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import Game, Mistake, Position, User


@pytest.fixture()
def session_factory() -> Iterator[sessionmaker[Session]]:
    # StaticPool so every connection in the test shares the same in-memory DB.
    # Without it, SQLite `:memory:` gives each new connection a fresh empty DB
    # and the API session can't see tables created by the fixture.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A session for arrange-step seeding inside a test. The override below
    creates its own session per request — committing here is what makes the
    seeded data visible to the API call."""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---- seeding helpers --------------------------------------------------------

def make_user(db: Session, username: str = "configured_user") -> User:
    user = User(lichess_username=username)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_game(
    db: Session,
    user: User,
    *,
    source: str = "lichess_online",
    source_game_id: str = "g0000001",
    user_color: str = "white",
    result: str = "1-0",
    played_at: datetime | None = None,
    has_evals: bool = True,
    analyzed: bool = False,
) -> Game:
    game = Game(
        user_id=user.id,
        source=source,
        source_game_id=source_game_id,
        user_color=user_color,
        white="alice" if user_color == "black" else user.lichess_username,
        black=user.lichess_username if user_color == "black" else "alice",
        result=result,
        time_control="300+0",
        played_at=played_at or datetime(2025, 6, 1, tzinfo=timezone.utc),
        pgn="[Event \"Test\"]\n\n1. e4 *\n",
        has_evals=has_evals,
        analyzed_at=datetime(2025, 6, 1, 12, tzinfo=timezone.utc) if analyzed else None,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return game


def make_position(
    db: Session,
    game: Game,
    *,
    ply: int,
    fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    san: str | None = None,
    uci: str | None = None,
    eval_cp: int | None = None,
    is_user_move: bool = False,
) -> Position:
    p = Position(
        game_id=game.id,
        ply=ply,
        fen=fen,
        san=san,
        uci=uci,
        is_user_move=is_user_move,
        eval_cp=eval_cp,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def make_mistake(
    db: Session,
    game: Game,
    *,
    ply: int = 5,
    severity: str = "blunder",
    suggested_step: int | None = 4,
    classified_step: int | None = None,
    classified_awareness: str | None = None,
    time_pressure: bool = False,
    endgame: bool = False,
) -> Mistake:
    m = Mistake(
        game_id=game.id,
        ply=ply,
        severity=severity,
        eval_before_cp=50,
        eval_after_cp=-500,
        winrate_before=55.0,
        winrate_after=10.0,
        winrate_drop=45.0,
        suggested_step=suggested_step,
        suggestion_confidence=0.8 if suggested_step else None,
        suggestion_debug={"step4": {"forcing": True}} if suggested_step == 4 else None,
        classified_step=classified_step,
        classified_awareness=classified_awareness,
        time_pressure_flag=time_pressure,
        transition_flag=False,
        endgame_flag=endgame,
    )
    if classified_step is not None or classified_awareness is not None:
        m.classified_at = datetime(2025, 6, 5, tzinfo=timezone.utc)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m
