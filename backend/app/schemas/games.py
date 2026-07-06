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
    """Per-game analysis outcome. The reconcile counters report what a
    (re-)analysis did to the Mistake rows: `mistakes_new` created,
    `mistakes_updated` refreshed in place (classifications untouched),
    `mistakes_removed` stale unclassified rows deleted, and
    `mistakes_preserved` classified rows kept even though the current rules
    no longer flag them. On a first analysis, new == detected."""

    game_id: int
    positions_created: int
    mistakes_detected: int
    skipped: bool
    reason: str | None = None
    mistakes_new: int = 0
    mistakes_updated: int = 0
    mistakes_removed: int = 0
    mistakes_preserved: int = 0


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


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ply: int
    fen: str
    san: str | None
    uci: str | None
    is_user_move: bool
    eval_cp: int | None
    mate_in: int | None
    clock_ms: int | None
    time_spent_ms: int | None


class GameListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[GameOut]
