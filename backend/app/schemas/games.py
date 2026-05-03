from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ImportRequest(BaseModel):
    source: str
    since: datetime | None = None
    limit: int | None = None


class ImportResponse(BaseModel):
    source: str
    imported: int
    skipped: int
    total_in_db: int


class AnalyzeResponse(BaseModel):
    game_id: int
    positions_created: int
    skipped: bool
    reason: str | None = None


class AnalyzePendingResponse(BaseModel):
    analyzed: int
    skipped: int
    results: list[AnalyzeResponse]


class GameOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    source_game_id: str
    user_color: str
    white: str
    black: str
    white_elo: int | None
    black_elo: int | None
    result: str
    time_control: str | None
    played_at: datetime | None
    has_evals: bool
    analyzed_at: datetime | None
    ingested_at: datetime
