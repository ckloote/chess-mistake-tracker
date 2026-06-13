"""Tests for the interactive position-analysis endpoint.

Engine-dependent assertions are skipped when no stockfish binary is on PATH
(same policy as test_stockfish_local). FEN-validation and no-engine paths are
tested unconditionally via a forced-bad-path settings override.
"""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.main import app

stockfish_path = shutil.which("stockfish")
requires_stockfish = pytest.mark.skipif(
    stockfish_path is None,
    reason="stockfish binary not installed; install it to run engine tests",
)

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_invalid_fen_returns_400(client: TestClient) -> None:
    """Bad FEN is rejected before any engine is launched."""
    resp = client.post("/api/v1/analysis/position", json={"fen": "not a fen"})
    assert resp.status_code == 400
    assert "Invalid FEN" in resp.json()["detail"]


def test_no_engine_returns_503(client: TestClient) -> None:
    """When stockfish can't be launched, the endpoint surfaces 503 rather than
    hanging or 500-ing. Force the failure with a bogus configured path so the
    test is deterministic regardless of whether stockfish is installed."""

    def _bad_settings() -> Settings:
        s = get_settings()
        return s.model_copy(update={"stockfish_path": "/nonexistent/stockfish"})

    app.dependency_overrides[get_settings] = _bad_settings
    try:
        resp = client.post("/api/v1/analysis/position", json={"fen": STARTING_FEN})
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert resp.status_code == 503
    assert "Stockfish" in resp.json()["detail"]


@requires_stockfish
def test_analyzes_starting_position(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/analysis/position",
        json={"fen": STARTING_FEN, "depth": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["turn"] == "white"
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert len(line["pv_uci"]) >= 1
    # SAN line should be as long as the UCI line (every move was legal).
    assert len(line["pv_san"]) == len(line["pv_uci"])
    # Starting position is roughly equal; not a forced mate.
    assert line["mate"] is None
    assert line["cp"] is not None


@requires_stockfish
def test_multipv_returns_multiple_lines(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/analysis/position",
        json={"fen": STARTING_FEN, "multipv": 3, "depth": 10},
    )
    assert resp.status_code == 200
    lines = resp.json()["lines"]
    assert len(lines) == 3
    # Distinct first moves across the lines.
    first_moves = {ln["pv_uci"][0] for ln in lines if ln["pv_uci"]}
    assert len(first_moves) == 3
