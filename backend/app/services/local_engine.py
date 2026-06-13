"""Shared lifecycle helper for the optional local Stockfish engine.

Both the batch analysis endpoints (best-move cascade) and the interactive
position-analysis endpoint need to spin up a Stockfish process when one is
available and degrade gracefully when it isn't. Centralizing that here keeps
the resolve → start → (yield) → stop dance in one place.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from backend.app.analyzers.stockfish_local import (
    StockfishLocalAnalyzer,
    resolve_stockfish_path,
)
from backend.app.config import Settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def maybe_local_engine(
    settings: Settings,
    depth: int | None = None,
) -> AsyncIterator[StockfishLocalAnalyzer | None]:
    """Yield a started StockfishLocalAnalyzer if a binary is resolvable, else
    None. Either way the caller gets a single object to pass through and an
    `async with` guarantee that any subprocess is cleaned up.

    `depth`, when given, overrides settings.stockfish_depth for this run — used
    by the interactive endpoint where the caller may want a per-request depth.
    """
    path = resolve_stockfish_path(settings.stockfish_path or None)
    if not path:
        yield None
        return
    analyzer = StockfishLocalAnalyzer(
        path=path,
        depth=depth if depth is not None else settings.stockfish_depth,
        time_ms=settings.stockfish_time_ms,
    )
    try:
        await analyzer.start()
    except (FileNotFoundError, OSError) as e:
        log.warning(
            "Stockfish-local feature configured but failed to start (%s); "
            "continuing without it.", e,
        )
        yield None
        return
    try:
        yield analyzer
    finally:
        await analyzer.stop()
