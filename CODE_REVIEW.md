# Code Review — 2026-07-06

Full review of docs (README.md, DESIGN.md, IMPLEMENTATION.md), the entire backend
(~5,600 lines), the entire frontend (~3,300 lines), and the test suite.

- **Reviewed at commit:** `cb1495a` ("Step 2: detect quiet best moves that create a material/mate threat"), branch `main`, working tree clean. All file/line references are relative to this commit.
- **Test status at review time:** `uv run pytest` → 148 passed. Frontend has no tests (`npm test` is a no-op echo).
- **Purpose of this file:** let another person or agent act on these findings without re-doing the analysis. Each finding carries location, evidence, and a suggested fix. Bugs B2 and B3 were verified by executing code (repro snippets included).

**Overall verdict:** a well-built codebase that tracks its spec unusually faithfully. Docs are kept in sync with implementation decisions; abstractions match the design; core-logic test coverage is good. The gaps are mostly the known-outstanding Phase 12, plus one serious data-loss footgun (B1) and two verified correctness bugs (B2, B3).

---

## 1. Phase status (per IMPLEMENTATION.md)

| Phase | Status |
|---|---|
| 1–11 (setup → dashboard/analytics) | **Done**, committed per phase (see git log) |
| 10.5 / Step-2 threat probe / local Stockfish | Done (post-MVP items pulled forward, documented in DESIGN.md) |
| 12 (settings UI, re-analyze button, polish, HOWTO) | **Not started** — Settings page is a placeholder (`frontend/src/pages/Settings.tsx`) |
| 13 (Docker, optional) | Not started (explicitly optional) |

---

## 2. Bugs

### B1 — Re-analysis silently destroys user classifications — **FIXED 2026-07-06**

- **Was:** `detect_mistakes()` ran `delete(Mistake).where(Mistake.game_id == game.id)` unconditionally, wiping `classified_step`, `classified_awareness`, `user_notes`, `classified_at`. Reachable via `POST /games/{id}/analyze` on an analyzed game and `POST /games/analyze-pending?force=true`.
- **Fix (implements F1):** `detect_mistakes` now reconciles rows by `(game_id, ply)` — detection fields updated in place, classifications never touched, auto-flags refreshed only while unclassified, stale unclassified rows deleted, stale **classified** rows kept frozen. Counters (`mistakes_new/updated/removed/preserved`) flow through `AnalysisResult` → `AnalyzeResponse`. Policy + rationale documented in DESIGN.md §"Re-analysis semantics"; regression tests in `backend/tests/test_mistake_detection.py` (§"Classification-preserving re-analysis", 7 tests). Stale docstrings in `api/games.py`, `services/analysis.py`, and both helper scripts updated.

### B2 — Study chapters starting from a custom FEN invert `is_user_move` — **FIXED 2026-07-06**

- **Was:** `is_user_move` and `_to_position_rows`' clock attribution (`backend/app/services/analysis.py`) assumed white moves on odd plies — only true from the standard starting position. `MoveList.tsx`'s `buildPairs` made the same parity assumption. Verified repro: a `[FEN "... b ..."]` chapter flagged every black move as the white user's; mistakes landed on the opponent's plies and clock deltas swapped colors.
- **Fix:** mover is now derived from the position's FEN side-to-move (`mover_color` in `services/analysis.py`; mover = opposite of the turn field) for both `is_user_move` and clock-delta attribution. `MoveList.tsx` derives mover and move number from the FEN the same way, pairing score-sheet rows correctly for black-first starts. Documented in DESIGN.md (§Data Model `positions` note) and IMPLEMENTATION.md Phase 4. Regression tests: FEN-start fixture in `test_analysis_service.py` (attribution + clocks) and `test_mistake_detection.py` (blunder lands on the black user's ply 3; nothing flagged for a white user). **Note:** any FEN-start study chapters analyzed before this fix carry inverted `is_user_move` rows — re-analyze them (`analyze-pending?force=true` is classification-preserving since the B1 fix).

### B3 — `mate_in == 0` always treated as "white wins" (MEDIUM, wrong-direction when hit) — VERIFIED

- **Where:** `backend/app/chess_utils/winrate.py` — `_white_winrate` maps `mate_in == 0` to `+MATE_CP_EQUIVALENT` ("just delivered"). Same collapse in `backend/app/services/mistake_detection.py:64` (`_eval_cp_for_storage`) and `backend/app/services/heuristics.py:51` (`_user_view_cp` treats `mate_in > 0` else negative — so 0 becomes −1000 there, inconsistent with winrate.py's +1000).
- **Root cause:** `%eval #-0` (black delivered mate) parses through python-chess to `mate_in = 0` — the sign is lost as an int.
- **Verified repro:** Fool's Mate PGN with `[%eval #-0]` on `Qh4#` → `winrate_for_color(..., "white")` returns **97.5%** for the checkmated white player.
- **Concrete failure:** a black user delivering mate annotated `#-0` sees winrate 97.5 → 2.5 on their own mating move → flagged as a blunder. Suppression rules don't catch it. Low frequency (Lichess usually omits eval on the mating move; the Step-4 `delivers_mate` special case in heuristics already fires from the board), but wrong-direction when it hits.
- **Suggested fix:** when `mate_in == 0`, the side to move in that position's FEN is the *mated* side — derive the winner from the FEN rather than assuming white. Requires threading the FEN (or the mated color) into `_white_winrate` callers; all call sites have the Position row in hand.

### B4 — `PATCH /settings` study IDs / aliases are dead controls — **FIXED 2026-07-06**

- **Was:** the settings API wrote `lichess_study_ids` / `study_player_aliases` to the `AppSettings` DB row, but `LichessStudySource.__init__` read them from env-backed `config.Settings` (`lru_cache`d for process lifetime) — PATCH edits changed nothing.
- **Fix:** the source registry (`backend/app/sources/registry.py`) now holds factories that take the `AppSettings` row; the import route passes `get_app_settings(db)`, so PATCH edits govern the next import with no restart. `LichessStudySource` no longer reads env config at all (env vars seed the DB row on first run only). Study ids are validated at PATCH time (`schemas/settings.py` → 422 on malformed ids), with the constructor check kept as a backstop surfaced as 400 on import. Tests: `test_source_registry.py` (registry wiring, 5 tests) plus PATCH-validation and an env-vs-DB divergence test in `test_api_settings.py`. Docs: DESIGN.md §Settings + §Source Abstractions + Open Question 1, IMPLEMENTATION.md Phase 3, `.env.example`, `config.py` comments.

### Minor bugs / nits

| # | Where | Issue |
|---|---|---|
| M1 | `frontend/src/pages/Mistakes.tsx` (game link), `frontend/src/pages/GameDetail.tsx` | Mistakes list links to `/games/{id}#ply={ply}` but GameDetail never reads the hash — dead affordance. Fix: parse `location.hash` into initial `activePly`. |
| M2 | `backend/app/services/mistake_detection.py:77-102` | Time-pressure clock threshold `max(60s, 10% of initial)` only scales **up**; in 3+0/5+0 blitz, 60s is a third/fifth of the game. Combined with the unconditional `<5s` rule, blitz games over-flag heavily. Consider scaling down for short TCs. |
| M3 | `backend/app/services/analysis.py:28` | `_TC_RE` requires `N+N`; a bare `"600"` TimeControl silently disables all clock math. |
| M4 | `backend/app/schemas/games.py` (`ImportRequest.since`) → `lichess_online.py` | Naive datetime → `.timestamp()` interprets as server-local time, not UTC. |
| M5 | `backend/app/services/analysis.py:174` + `heuristics.py:338` | `analyze_pending` docstring claims a shared httpx client, but the API route passes `cloud_analyzer=None`, so every cloud call constructs and closes its own `httpx.AsyncClient`. |
| M6 | `frontend/src/api/analysis.ts` (`formatScore`) | Identical-branch ternary (`m > 0 ? \`#${m}\` : \`#${m}\``) — dead code, output happens to be correct. |
| M7 | `frontend/src/components/ExploreBoard.tsx` (`playUci`) | Always auto-queens; clicking an engine line containing an underpromotion (e.g. `e7e8n`) plays the wrong move. |
| M8 | `frontend/src/api/analysis.ts` (`useAnalyzePosition`) | Query cache key is `[fen, multipv]` but not `depth` — latent collision if per-request depth is ever passed. |
| M9 | `backend/app/api/mistakes.py` (`update_mistake`) | Clearing both classification fields to null leaves `classified_at` set — row leaves the unclassified queue carrying no classification. |
| M10 | `Makefile` (`clean`) | Deletes `data/*.db` (classification data) together with `.venv`. Worth a confirm or a separate `clean-db` target. |

---

## 3. Spec-conformance gaps

1. ~~**"Needs Lichess analysis" re-fetch workflow is broken.**~~ **FIXED 2026-07-06** (implements F2): `fetch_game_by_id` implemented in both sources (protocol signature now `(user, game_id) -> GameRecord | None` — the original couldn't resolve `user_color`; DESIGN.md updated), plus `refresh_game` service and `POST /games/{id}/refresh`. Refresh updates PGN/`has_evals`/metadata in place and clears `analyzed_at` only when the PGN changed; upstream 404 → 404, user-no-longer-a-player → 409, other upstream errors → 502. Also un-freezes grown study chapters. UI affordance (refresh action on the "Needs Lichess analysis" pill + Lichess deep link) remains a Phase 12 item.
2. **Phase 12 outstanding (expected):** Settings page placeholder; no import/analyze/re-analyze controls anywhere in the UI (Games empty-state says to use `curl`); no re-analysis warning; no HOWTO.md. FastAPI does not serve `frontend/dist/` despite DESIGN §"Production-style local serve" and the comment in `frontend/src/api/client.ts`; `GET /games/import/status/{job_id}` doesn't exist (acceptable — ingestion is synchronous).
3. **Stats filters missing.** Phase 11 acceptance: "Filters (date range, source) update all charts." `/stats/*` endpoints accept no filters. Also missing from the Phase 11 deliverables list: severity-distribution-by-step chart; time-pressure correlation *by month* (implemented as an overall proportion); dashboard "recent games" strip.
4. **`suggestion_debug` doesn't record "all that fired."** DESIGN §Tie-breaking says record every detector that fired; the cascade (`backend/app/services/heuristics.py:364-401`) short-circuits at first fire, so lower-priority detectors are never evaluated. Debug shows "what ran until something fired."
5. **No frontend tests.** DESIGN's stack table names Vitest; IMPLEMENTATION exempts UI tests for MVP. Borderline, but `buildPairs` (MoveList) and ExploreBoard line/cursor logic are pure and unit-testable.

Deviations that are **documented and fine** (no action): Step 4 uses the actual opponent reply, not an engine lookup; Step 1 is the recapture-the-mover approximation; study dedup by chapter ID; mate ≈ ±1000cp; whole-game Stockfish analysis deferred (`StockfishLocalAnalyzer.analyze_game` raises).

---

## 4. Design assessment

**Strengths (keep):** protocol-based `GameSource`/`Analyzer` with honest silent-degradation contracts; pure module-scope functions (parsing, winrate, SEE) split from orchestration; SEE implementation is textbook-correct incl. x-rays and en passant (`backend/app/chess_utils/see.py`); `ucinewgame`-per-position reproducibility + MultiPV matching between batch heuristic and Explore board (`BEST_MOVE_MULTIPV = 3` must stay equal to the frontend's `multipv: 3`); tunables in a DB singleton; docs updated with "as implemented" notes. The docs-as-living-spec discipline is the best thing about this repo.

**Concerns (ordered by practical weight):**

1. **Long-running work inside a single HTTP request on the event loop.** `analyze-pending` over N games with Stockfish depth 15 (plus a null-move probe per quiet-best mistake) can take minutes: no job model, no progress reporting, and blocking sync SQLAlchemy calls inside `async def` handlers stall the loop for concurrent requests (the Explore board's `/analysis/position` will feel it). First wall when importing a large backlog. DESIGN already anticipated the fix (job + status endpoint).
2. **One Stockfish process per Explore request.** `maybe_local_engine` (`backend/app/services/local_engine.py`) spawns/handshakes/kills per position change. `ucinewgame` already guarantees reproducibility, so a long-lived app-lifespan engine behind an asyncio lock would cut Explore latency with identical results.
3. **Ingestion never updates existing rows** (see gap 1) — dedup-by-ID needs a companion "refresh" concept.
4. Small: `_get_best_move` cache is per-run only; `STEP_LABELS`/severity-glyph maps duplicated across four frontend files vs. the shared ones in `frontend/src/api/stats.ts`.

---

## 5. Recommended features (highest leverage first)

- **F1 — Classification-preserving re-analysis** (fixes B1): ~~re-detect, diff by `(game_id, ply)`, carry classifications onto survivors, report "N new / M removed / K preserved."~~ **DONE 2026-07-06** — see B1. Phase 12's "Re-analyze all" button is now safe to build on top.
- **F2 — Game refresh** (fixes gap 1): ~~`POST /games/{id}/refresh` — implement `fetch_game_by_id`, update PGN/`has_evals`, clear `analyzed_at`.~~ **DONE 2026-07-06** — see gap 1. The "Request analysis on Lichess" deep link + refresh button in the Games UI go with Phase 12.
- **F3 — Whole-game local Stockfish analysis** (`StockfishLocalAnalyzer.analyze_game`): makes `has_evals=false` games and all study chapters processable without Lichess; prerequisite for chess.com support. Already noted as the next step in project memory/DESIGN.
- **F4 — Filtered analytics:** shared filter dependency (date range, source, color, severity, time control) across `/stats/*`; frontend layout is ready. Answers "do my patterns differ OTB vs online / blitz vs classical."
- **F5 — Drill mode** (from the existing backlog): re-present classified mistake positions as find-the-move puzzles ordered by weakest Layer A × B cell, spaced repetition on misses. Closes the diagnosis → training loop; today the prescription is text-only.
- **F6 — Smaller:** import/analyze buttons in the UI (Phase 12); honor `#ply=` in GameDetail (M1); "heuristic accuracy" stat (suggested-vs-classified agreement rate over time); per-game eval graph in review (data already in `positions`); CSV/PDF export of classified mistakes for a coach.

---

## 6. Suggested order of work

1. ~~B1 / F1 (classification-preserving re-analysis)~~ **DONE 2026-07-06.**
2. ~~B2 (FEN-start parity)~~ **DONE 2026-07-06.**
3. ~~B4 (settings → study source wiring)~~ **DONE 2026-07-06** — the Phase 12 settings UI can now build on it.
4. ~~F2 (game refresh)~~ **DONE 2026-07-06.**
5. B3 + minor bugs opportunistically alongside the above; Phase 12 UI next (all backend prerequisites in place).
6. F3 → F4 → F5 as feature work.

## 7. Verification notes for the next agent

- Repro for B2/B3 (run with `uv run python`): parse a PGN through `backend.app.analyzers.lichess_pgn.parse_pgn_for_positions`, then call `backend.app.services.analysis.is_user_move` (B2) or `backend.app.chess_utils.winrate.winrate_for_color` on a `[%eval #-0]` final ply (B3).
- The dev server is started by the user in their own terminal — don't background it.
- `uv run pytest` from repo root; pytest config lives in `pyproject.toml` (`testpaths = backend/tests`, asyncio auto mode).
