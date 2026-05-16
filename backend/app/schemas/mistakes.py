from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.games import GameOut, PositionOut


class MistakeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    game_id: int
    ply: int
    severity: str
    eval_before_cp: int | None
    eval_after_cp: int | None
    winrate_before: float
    winrate_after: float
    winrate_drop: float
    best_move_uci: str | None
    best_move_san: str | None
    suggested_step: int | None
    suggestion_confidence: float | None
    suggestion_debug: dict | None
    classified_step: int | None
    classified_awareness: str | None
    time_pressure_flag: bool
    transition_flag: bool
    endgame_flag: bool
    user_notes: str | None
    classified_at: datetime | None


class MistakeListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MistakeOut]


class GameDetailOut(GameOut):
    """Lives here (rather than schemas/games.py) so it can reference MistakeOut
    without creating a cyclic import: games.py is the leaf module, mistakes.py
    builds on it."""

    pgn: str
    positions: list[PositionOut]
    mistakes: list[MistakeOut]


class MistakeDetailOut(MistakeOut):
    """Mistake plus the context the review UI needs to render the position:
    prev (P_before), pos (P_after_user_move), next (P_after_opp_response if any),
    and a small slice of the parent game."""

    game: GameOut
    position_before: PositionOut | None
    position_at_move: PositionOut | None
    position_after_response: PositionOut | None


class MistakeUpdate(BaseModel):
    """All fields optional — PATCH semantics. Setting classified_step or
    classified_awareness stamps classified_at server-side."""

    classified_step: int | None = Field(default=None, ge=1, le=4)
    classified_awareness: str | None = Field(default=None, pattern="^(got_it_wrong|didnt_see_it)$")
    user_notes: str | None = None
    time_pressure_flag: bool | None = None
    transition_flag: bool | None = None
    endgame_flag: bool | None = None
