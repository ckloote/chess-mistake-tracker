from sqlalchemy import JSON, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class AppSettings(Base):
    """Singleton row (id=1) holding tunable settings. Bootstrapped from
    config.Settings defaults on first read. The Settings class still owns
    boot-time concerns (DB path, configured Lichess username)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    winrate_inaccuracy: Mapped[float] = mapped_column(Float, nullable=False)
    winrate_mistake: Mapped[float] = mapped_column(Float, nullable=False)
    winrate_blunder: Mapped[float] = mapped_column(Float, nullable=False)

    suppress_below: Mapped[float] = mapped_column(Float, nullable=False)
    suppress_above_before: Mapped[float] = mapped_column(Float, nullable=False)
    suppress_above_after: Mapped[float] = mapped_column(Float, nullable=False)

    lichess_study_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    study_player_aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
