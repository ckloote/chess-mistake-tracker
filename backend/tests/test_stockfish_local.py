"""Integration tests for the local Stockfish analyzer. Skipped when no
stockfish binary is on PATH — the codebase deliberately treats stockfish
as an optional capability, so CI without it shouldn't fail."""
from __future__ import annotations

import shutil

import pytest

from backend.app.analyzers.stockfish_local import (
    StockfishLocalAnalyzer,
    resolve_stockfish_path,
)

stockfish_path = shutil.which("stockfish")
requires_stockfish = pytest.mark.skipif(
    stockfish_path is None,
    reason="stockfish binary not installed; install it to run engine tests",
)


def test_resolve_stockfish_path_prefers_configured_value() -> None:
    """Configured paths win even when no binary exists — the caller's
    responsibility is to surface that as "feature disabled" or an error."""
    assert resolve_stockfish_path("/explicit/path") == "/explicit/path"


def test_resolve_stockfish_path_falls_back_to_path_lookup() -> None:
    # Whether stockfish is installed or not, an empty configured path
    # should yield shutil.which's answer (None or a real path).
    assert resolve_stockfish_path("") == shutil.which("stockfish")
    assert resolve_stockfish_path(None) == shutil.which("stockfish")


@requires_stockfish
async def test_analyzer_finds_a_legal_best_move_for_starting_position() -> None:
    starting_fen = (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    )
    async with StockfishLocalAnalyzer(
        path=stockfish_path,  # type: ignore[arg-type]
        depth=10,  # shallow enough to keep this test fast
    ) as engine:
        results = await engine.analyze_position(starting_fen)
    assert len(results) == 1
    best = results[0]
    assert len(best.pv) >= 1
    # Most common starting moves are e4, d4, Nf3, c4. Don't constrain too
    # tightly — engine choice can vary by version. Just sanity-check format.
    assert len(best.pv[0]) >= 4
    # The starting position is approximately equal; cp should be near zero,
    # mate should be None.
    assert best.mate is None
    assert best.cp is not None
    assert -200 < best.cp < 200


@requires_stockfish
async def test_analyzer_returns_empty_for_garbage_fen() -> None:
    async with StockfishLocalAnalyzer(
        path=stockfish_path,  # type: ignore[arg-type]
        depth=5,
    ) as engine:
        results = await engine.analyze_position("not a fen")
    assert results == []


@requires_stockfish
async def test_analyzer_returns_empty_before_start() -> None:
    """Without start() / `async with`, the engine isn't running — calling
    analyze_position should silently return [] rather than raising."""
    engine = StockfishLocalAnalyzer(
        path=stockfish_path,  # type: ignore[arg-type]
        depth=5,
    )
    results = await engine.analyze_position(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    )
    assert results == []
