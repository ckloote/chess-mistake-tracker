from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    chess_db_path: str = "./data/chess.db"
    lichess_username: str = ""
    lichess_study_ids: list[str] = Field(default_factory=list)

    winrate_inaccuracy: float = 5.0
    winrate_mistake: float = 10.0
    winrate_blunder: float = 20.0

    suppress_below: float = 30.0
    suppress_above_before: float = 90.0
    suppress_above_after: float = 80.0

    @field_validator("lichess_study_ids", mode="before")
    @classmethod
    def _split_study_ids(cls, v: object) -> object:
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
