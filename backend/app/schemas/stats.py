from pydantic import BaseModel


class StepCount(BaseModel):
    step: int
    count: int


class AwarenessCount(BaseModel):
    awareness: str
    count: int


class SeverityCount(BaseModel):
    severity: str
    count: int


class SummaryOut(BaseModel):
    total_games: int
    total_mistakes: int
    classified: int
    unclassified: int
    by_suggested_step: list[StepCount]
    by_classified_step: list[StepCount]
    by_awareness: list[AwarenessCount]
    by_severity: list[SeverityCount]


class BreakdownItem(BaseModel):
    label: str
    count: int


class BreakdownOut(BaseModel):
    by: str
    items: list[BreakdownItem]


class PrescriptionItem(BaseModel):
    step: int
    awareness: str
    count: int
    share: float  # of classified mistakes
    suggestion: str


class PrescriptionOut(BaseModel):
    classified_mistakes: int
    items: list[PrescriptionItem]
