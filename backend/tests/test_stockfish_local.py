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


# ---- Whole-game analysis (F3) ----------------------------------------------

# Scholar's mate: no %eval annotations (the case whole-game analysis exists
# for), one %clk to prove clock passthrough.
SCHOLARS_MATE_PGN = """\
[Event "Test"]
[White "user"]
[Black "opponent"]
[Result "1-0"]

1. e4 e5 2. Bc4 { [%clk 0:04:55] } Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
"""


@requires_stockfish
async def test_analyze_game_fills_evals_for_every_ply() -> None:
    async with StockfishLocalAnalyzer(
        path=stockfish_path,  # type: ignore[arg-type]
        depth=8,  # shallow: enough to see mate-in-1 and keep the test fast
    ) as engine:
        rows = await engine.analyze_game(SCHOLARS_MATE_PGN)

    assert [r.ply for r in rows] == list(range(8))  # ply 0 + 7 moves
    # Every non-terminal position got an engine eval (cp XOR mate).
    for r in rows[:-1]:
        assert (r.eval_cp is None) != (r.mate_in is None)
    # PGN-borne fields survive: SAN/UCI and the one %clk annotation.
    assert rows[3].san == "Bc4"
    assert rows[3].clock_ms == 295_000
    assert rows[0].san is None and rows[0].uci is None
    # After 3...Nf6 white mates in 1 -> white-POV Mate(+1).
    assert rows[6].mate_in == 1
    # Terminal checkmate is settled by rule, not engine: mate_in == 0
    # (winrate code derives the winner from the FEN's side-to-move).
    assert rows[7].san == "Qxf7#"
    assert rows[7].mate_in == 0 and rows[7].eval_cp is None


@requires_stockfish
async def test_analyze_game_returns_empty_before_start_and_for_bad_pgn() -> None:
    engine = StockfishLocalAnalyzer(
        path=stockfish_path,  # type: ignore[arg-type]
        depth=5,
    )
    assert await engine.analyze_game(SCHOLARS_MATE_PGN) == []  # not started
    async with engine:
        assert await engine.analyze_game("") == []  # unparseable
