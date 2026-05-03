from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
