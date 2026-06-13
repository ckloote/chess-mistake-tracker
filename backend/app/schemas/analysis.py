"""Schemas for the interactive position-analysis endpoint."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzePositionRequest(BaseModel):
    fen: str = Field(description="FEN of the position to analyze.")
    multipv: int = Field(
        default=1,
        ge=1,
        le=5,
        description="How many top lines to return (1 = best move only).",
    )
    depth: int | None = Field(
        default=None,
        ge=1,
        le=30,
        description="Override the configured search depth for this request.",
    )


class AnalyzedLine(BaseModel):
    """One engine line. cp/mate are white-POV (positive = white is better),
    matching the convention used elsewhere in the codebase."""

    cp: int | None
    mate: int | None
    pv_uci: list[str]
    pv_san: list[str]
    depth: int | None


class PositionAnalysisOut(BaseModel):
    fen: str
    turn: str  # "white" | "black" — whose move it is in `fen`
    lines: list[AnalyzedLine]
