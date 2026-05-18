"""Local Stockfish analyzer.

Fills the coverage gap left by LichessCloudEvalAnalyzer: cloud-eval only has
positions someone has previously analyzed, so a user's later-middlegame and
endgame positions usually return nothing. This analyzer drives a local
Stockfish process via python-chess's UCI helpers and answers "what's the best
move from this FEN" for any legal position.

Lifecycle: one process is spawned via start() at the beginning of an analyze
run and stopped via stop() at the end, so the cost of UCI handshake +
isready is paid once per run rather than once per position. Use as an async
context manager when possible.
"""
from __future__ import annotations

import asyncio
import logging
import shutil

import chess
import chess.engine

from backend.app.analyzers.base import EvalResult

log = logging.getLogger(__name__)


def resolve_stockfish_path(configured: str | None) -> str | None:
    """Best-effort resolution of a stockfish binary.

    If `configured` is a non-empty string it's used as-is. Otherwise we look
    for `stockfish` on PATH. Returns None when neither is set or found —
    callers should treat that as "feature disabled" and skip silently.
    """
    if configured:
        return configured
    return shutil.which("stockfish")


class StockfishLocalAnalyzer:
    name = "stockfish_local"

    def __init__(
        self,
        path: str,
        depth: int | None = 15,
        time_ms: int | None = None,
    ) -> None:
        """`time_ms` (when > 0) overrides `depth`; `depth` is used otherwise.
        Keeping both lets the same instance answer "thorough" or "cheap"
        depending on what the caller knows about the position pool."""
        self._path = path
        self._depth = depth
        self._time_ms = time_ms
        self._engine: chess.engine.UciProtocol | None = None
        self._transport: asyncio.SubprocessTransport | None = None

    @property
    def supports_per_position(self) -> bool:
        return True

    async def __aenter__(self) -> "StockfishLocalAnalyzer":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        """Spawn the Stockfish process. Idempotent: a second call is a no-op.
        Raises if the binary can't be launched — callers using `resolve_stockfish_path`
        first won't typically hit this."""
        if self._engine is not None:
            return
        self._transport, self._engine = await chess.engine.popen_uci(self._path)

    async def stop(self) -> None:
        if self._engine is None:
            return
        try:
            await self._engine.quit()
        except (chess.engine.EngineError, asyncio.CancelledError) as e:
            # Process already gone or canceled; nothing to clean up further.
            log.debug("Stockfish quit raised %s; ignoring.", e)
        finally:
            self._engine = None
            self._transport = None

    def _limit(self) -> chess.engine.Limit:
        if self._time_ms and self._time_ms > 0:
            return chess.engine.Limit(time=self._time_ms / 1000)
        return chess.engine.Limit(depth=self._depth or 15)

    async def analyze_position(
        self, fen: str, multipv: int = 1
    ) -> list[EvalResult]:
        """Returns EvalResults for the top `multipv` moves from `fen`. Returns
        an empty list when the engine isn't running, the FEN is invalid, or
        the engine errors — same shape as the cloud analyzer's silent-fail
        contract, so the heuristic's cascade logic works without special cases."""
        if self._engine is None:
            return []
        try:
            board = chess.Board(fen)
        except ValueError:
            return []

        try:
            info = await self._engine.analyse(
                board,
                self._limit(),
                multipv=multipv if multipv > 1 else None,
            )
        except (chess.engine.EngineError, asyncio.CancelledError) as e:
            log.warning("stockfish analyse failed for fen=%r: %s", fen, e)
            return []

        # python-chess returns a single dict when multipv is unset and a list
        # of dicts when multipv >= 1. Normalize so downstream code is uniform.
        entries = info if isinstance(info, list) else [info]

        results: list[EvalResult] = []
        for entry in entries:
            score = entry.get("score")
            pv = entry.get("pv") or []
            cp: int | None = None
            mate: int | None = None
            if score is not None:
                # POV-normalize to white's perspective so the value matches
                # the convention used elsewhere in the codebase (positive =
                # white winning). Detection logic flips for color separately.
                white_score = score.white()
                if white_score.is_mate():
                    mate = white_score.mate()
                else:
                    cp = white_score.score()
            results.append(
                EvalResult(
                    cp=cp,
                    mate=mate,
                    pv=[m.uci() for m in pv],
                    depth=entry.get("depth"),
                )
            )
        return results

    async def analyze_game(self, pgn: str) -> list:
        """Full-game analysis (would replace the PGN eval reader for games
        without embedded evals) is deferred. For now this analyzer only
        backs the per-position heuristic best-move lookup; whole-game
        analysis joins the post-MVP queue alongside the chess.com source."""
        raise NotImplementedError(
            "StockfishLocalAnalyzer.analyze_game is not implemented yet — "
            "this analyzer currently fills the per-position best-move gap only."
        )
