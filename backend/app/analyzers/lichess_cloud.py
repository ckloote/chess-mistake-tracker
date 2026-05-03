"""Lichess cloud-eval analyzer.

The cloud endpoint returns evals for any position someone has previously
analyzed. Most well-trodden positions are there; obscure middlegame positions
in a specific user's games often aren't. This analyzer surfaces None silently
in that case so the caller can fall through to a default heuristic.
"""
from __future__ import annotations

import logging

import httpx

from backend.app.analyzers.base import EvalResult

LICHESS_CLOUD_EVAL_URL = "https://lichess.org/api/cloud-eval"
log = logging.getLogger(__name__)


def _parse_pv_response(payload: dict) -> list[EvalResult]:
    pvs = payload.get("pvs") or []
    depth = payload.get("depth")
    out: list[EvalResult] = []
    for pv in pvs:
        moves = (pv.get("moves") or "").split()
        cp = pv.get("cp")
        mate = pv.get("mate")
        out.append(EvalResult(cp=cp, mate=mate, pv=moves, depth=depth))
    return out


class LichessCloudEvalAnalyzer:
    name = "lichess_cloud"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @property
    def supports_per_position(self) -> bool:
        return True

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]:
        """Returns list of EvalResults from the cloud, or [] if Lichess doesn't
        know this position. Network errors and 404s are swallowed (returned as
        empty) — heuristics treat missing cloud data as "fall through"."""
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        try:
            response = await client.get(
                LICHESS_CLOUD_EVAL_URL,
                params={"fen": fen, "multiPv": multipv},
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            return _parse_pv_response(response.json())
        except httpx.HTTPError as e:
            log.warning("cloud-eval failed for fen=%r: %s", fen, e)
            return []
        finally:
            if owns_client:
                await client.aclose()

    async def analyze_game(self, pgn: str) -> list:
        # Cloud eval is per-position; analyzing whole games is the PGN
        # analyzer's job.
        raise NotImplementedError("LichessCloudEvalAnalyzer is per-position only.")
