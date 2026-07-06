"""Recompute the persisted best move for existing mistakes, in place.

This re-runs only the heuristic suggestion pass — `assign_heuristic_suggestions`
mutates best_move_uci / best_move_san / suggested_step on the existing rows and
never touches the classified_* columns. `analyze-pending --force` also
preserves classifications now (detection reconciles Mistake rows in place; see
DESIGN.md §"Re-analysis semantics"), but it re-runs the full pipeline
(position rebuild + detection). This script remains the cheaper option when
only the best-move/suggestion source changed.

Use after changing the best-move source (e.g. the cloud→local-first flip) so
the review-mode arrow matches what the local Explore board shows. Idempotent.

Run: `uv run python scripts/backfill_best_move.py`
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.db import SessionLocal
from backend.app.models import Game, Mistake
from backend.app.services.heuristics import assign_heuristic_suggestions
from backend.app.services.local_engine import maybe_local_engine


async def main() -> int:
    settings = get_settings()
    with SessionLocal() as session:
        games = session.scalars(
            select(Game).where(Game.analyzed_at.is_not(None)).order_by(Game.id)
        ).all()

        async with maybe_local_engine(settings) as local:
            if local is None:
                print(
                    "No local Stockfish resolved (set STOCKFISH_PATH or install "
                    "stockfish). Best moves would fall back to cloud-eval; "
                    "aborting so we don't re-persist the inconsistent source."
                )
                return 1

            total_games = 0
            total_mistakes = 0
            for game in games:
                mistakes = list(
                    session.scalars(
                        select(Mistake)
                        .where(Mistake.game_id == game.id)
                        .order_by(Mistake.ply)
                    ).all()
                )
                if not mistakes:
                    continue
                await assign_heuristic_suggestions(
                    session, game, mistakes, local_analyzer=local
                )
                total_games += 1
                total_mistakes += len(mistakes)
                print(f"  game {game.id}: refreshed {len(mistakes)} mistakes")

            session.commit()

    print(
        f"Backfilled best moves for {total_mistakes} mistakes across "
        f"{total_games} games (classifications preserved)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
