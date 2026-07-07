from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.sources.lichess_study import validate_study_id


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Read-only context for the settings page: the boot-time username from the
    # env (changing it implies re-seeding, so there's no PATCH for it).
    lichess_username: str = ""

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
    to 0–100 because they're win-percentage points. Study ids are validated at
    write time so a bad id fails here (422) rather than at the next import."""

    winrate_inaccuracy: float | None = Field(default=None, ge=0, le=100)
    winrate_mistake: float | None = Field(default=None, ge=0, le=100)
    winrate_blunder: float | None = Field(default=None, ge=0, le=100)
    suppress_below: float | None = Field(default=None, ge=0, le=100)
    suppress_above_before: float | None = Field(default=None, ge=0, le=100)
    suppress_above_after: float | None = Field(default=None, ge=0, le=100)
    lichess_study_ids: list[str] | None = None
    study_player_aliases: list[str] | None = None

    @field_validator("lichess_study_ids")
    @classmethod
    def _study_ids_look_like_lichess_ids(cls, v: list[str] | None) -> list[str] | None:
        for study_id in v or []:
            validate_study_id(study_id)  # ValueError -> 422 with the message
        return v
