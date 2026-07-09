from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    chess_db_path: str = "./data/chess.db"
    lichess_username: str = ""
    # Seeds users.chesscom_username on first run only (scripts/seed.py); after
    # that the DB governs and edits happen via the Settings page.
    chesscom_username: str = ""
    # NoDecode skips pydantic-settings' default JSON decode of complex env types,
    # so the comma-separated string falls through to the validator below.
    # NOTE: study ids and aliases here only SEED the AppSettings DB row on
    # first run. After that the DB governs (PATCH /settings edits it) and
    # these env values are never consulted again.
    lichess_study_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Alternative player names to treat as the configured user when matching
    # study chapter [White]/[Black] tags — primarily for OTB studies where the
    # user is recorded by real name or initials, not by Lichess username.
    study_player_aliases: Annotated[list[str], NoDecode] = Field(default_factory=list)

    winrate_inaccuracy: float = 5.0
    winrate_mistake: float = 10.0
    winrate_blunder: float = 20.0

    suppress_below: float = 30.0
    suppress_above_before: float = 90.0
    suppress_above_after: float = 80.0

    # Stockfish-local: empty path → resolve via shutil.which("stockfish").
    # When even that returns None, the local fallback is silently disabled.
    stockfish_path: str = ""
    # Either depth OR time-budget per position. When time_ms > 0 it wins.
    stockfish_depth: int = 15
    stockfish_time_ms: int = 0

    @field_validator("lichess_study_ids", "study_player_aliases", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.chess_db_path}"

    def ensure_data_dir(self) -> None:
        Path(self.chess_db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_data_dir()
    return settings
