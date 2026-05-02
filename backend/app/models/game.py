from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "source_game_id", name="uq_game_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_game_id: Mapped[str] = mapped_column(String, nullable=False)
    user_color: Mapped[str] = mapped_column(String, nullable=False)
    white: Mapped[str] = mapped_column(String, nullable=False)
    black: Mapped[str] = mapped_column(String, nullable=False)
    white_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    black_elo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String, nullable=False)
    time_control: Mapped[str | None] = mapped_column(String, nullable=True)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pgn: Mapped[str] = mapped_column(Text, nullable=False)
    has_evals: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
