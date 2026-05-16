from pydantic import BaseModel, ConfigDict, Field


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    winrate_inaccuracy: float
    winrate_mistake: float
    winrate_blunder: float
    suppress_below: float
    suppress_above_before: float
    suppress_above_after: float
    lichess_study_ids: list[str]
    study_player_aliases: list[str]


class SettingsUpdate(BaseModel):
    """All fields optional (PATCH semantics). Threshold fields are constrained
    to 0–100 because they're win-percentage points."""

    winrate_inaccuracy: float | None = Field(default=None, ge=0, le=100)
    winrate_mistake: float | None = Field(default=None, ge=0, le=100)
    winrate_blunder: float | None = Field(default=None, ge=0, le=100)
    suppress_below: float | None = Field(default=None, ge=0, le=100)
    suppress_above_before: float | None = Field(default=None, ge=0, le=100)
    suppress_above_after: float | None = Field(default=None, ge=0, le=100)
    lichess_study_ids: list[str] | None = None
    study_player_aliases: list[str] | None = None
