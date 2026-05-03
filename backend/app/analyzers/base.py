from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class EvalResult:
    """Single-position evaluation. Either eval_cp or mate_in is set; never both."""

    cp: int | None
    mate: int | None
    pv: list[str]  # principal variation as UCI strings
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class PositionEval:
    """Per-ply view of a game. ply 0 is the starting position (no move played
    yet); san/uci/eval/clock are all None for ply 0."""

    ply: int
    fen: str
    san: str | None
    uci: str | None
    eval_cp: int | None
    mate_in: int | None
    clock_ms: int | None


@runtime_checkable
class Analyzer(Protocol):
    name: str

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]: ...

    async def analyze_game(self, pgn: str) -> list[PositionEval]: ...

    @property
    def supports_per_position(self) -> bool: ...
