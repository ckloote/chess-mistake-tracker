from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Mistake(Base):
    __tablename__ = "mistakes"
    __table_args__ = (
        UniqueConstraint("game_id", "ply", name="uq_mistake_game_ply"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)

    eval_before_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_after_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    winrate_before: Mapped[float] = mapped_column(Float, nullable=False)
    winrate_after: Mapped[float] = mapped_column(Float, nullable=False)
    winrate_drop: Mapped[float] = mapped_column(Float, nullable=False)

    best_move_uci: Mapped[str | None] = mapped_column(String, nullable=True)
    best_move_san: Mapped[str | None] = mapped_column(String, nullable=True)

    suggested_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggestion_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggestion_debug: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    classified_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classified_awareness: Mapped[str | None] = mapped_column(String, nullable=True)

    time_pressure_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transition_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endgame_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
