from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (Index("ix_position_game_ply", "game_id", "ply"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), nullable=False)
    ply: Mapped[int] = mapped_column(Integer, nullable=False)
    fen: Mapped[str] = mapped_column(Text, nullable=False)
    san: Mapped[str | None] = mapped_column(String, nullable=True)
    uci: Mapped[str | None] = mapped_column(String, nullable=True)
    is_user_move: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eval_cp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mate_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_spent_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
