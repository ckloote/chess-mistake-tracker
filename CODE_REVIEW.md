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

### B3 — `mate_in == 0` always treated as "white wins" — **FIXED 2026-07-07**

- **Was:** `%eval #-0` (black delivered mate) parses to the int `mate_in = 0` with the sign lost; `winrate.py` read that as white-wins (+1000) while `heuristics._user_view_cp` read it as −1000 — so a black user delivering mate saw their mating move flagged as a ~95-point blunder (verified with Fool's Mate).
- **Fix:** new `mate_zero_white_view_cp(fen)` in `chess_utils/winrate.py` — in a checkmate position the FEN's side-to-move is the mated side, so the winner is derived from the FEN. All three mate-collapsing helpers (`winrate_for_color`, detection's `_eval_cp_for_storage`, heuristics' `_user_view_cp`) now take the position's FEN and agree; without a FEN the legacy white-wins assumption remains as documented fallback. Regression tests: FEN-disambiguation units in `test_winrate.py` plus Fool's-Mate end-to-end in `test_mistake_detection.py` (delivering mate not flagged; getting mated flags the mover's move as a Step-4 blunder). DESIGN.md §"Win% from centipawn eval" and the `positions.mate_in` column note updated.

### B4 — `PATCH /settings` study IDs / aliases are dead controls — **FIXED 2026-07-06**

- **Was:** the settings API wrote `lichess_study_ids` / `study_player_aliases` to the `AppSettings` DB row, but `LichessStudySource.__init__` read them from env-backed `config.Settings` (`lru_cache`d for process lifetime) — PATCH edits changed nothing.
- **Fix:** the source registry (`backend/app/sources/registry.py`) now holds factories that take the `AppSettings` row; the import route passes `get_app_settings(db)`, so PATCH edits govern the next import with no restart. `LichessStudySource` no longer reads env config at all (env vars seed the DB row on first run only). Study ids are validated at PATCH time (`schemas/settings.py` → 422 on malformed ids), with the constructor check kept as a backstop surfaced as 400 on import. Tests: `test_source_registry.py` (registry wiring, 5 tests) plus PATCH-validation and an env-vs-DB divergence test in `test_api_settings.py`. Docs: DESIGN.md §Settings + §Source Abstractions + Open Question 1, IMPLEMENTATION.md Phase 3, `.env.example`, `config.py` comments.

### Minor bugs / nits — **ALL FIXED 2026-07-07**

| # | Where | Issue → Fix |
|---|---|---|
| M1 | `Mistakes.tsx` / `GameDetail.tsx` | `#ply=` hash was never read → GameDetail now opens at the hashed ply (clamped once positions load). |
| M2 | `mistake_detection.py` | Low-clock threshold had a 60s floor that over-flagged blitz → now a straight 10% of initial time, scaled both directions (DESIGN.md time-pressure section updated). The `<5s` rule stays — it's explicit in DESIGN.md. |
| M3 | `analysis.py` | Bare `"600"` TimeControl disabled clock math → `_TC_RE` now accepts a missing increment as `+0`. |
| M4 | `lichess_online.py` | Naive `since` datetime read as server-local → now treated as UTC. |
| M5 | `analysis.py` | `analyze_pending` now actually builds one shared `httpx.AsyncClient` when the caller doesn't supply an analyzer, matching its docstring. |
| M6 | `analysis.ts` (`formatScore`) | Identical-branch ternary collapsed. |
| M7 | `ExploreBoard.tsx` (`playUci`) | Engine-line clicks now pass the UCI's promotion piece; board drags still auto-queen. |
| M8 | `analysis.ts` (`useAnalyzePosition`) | `depth` added to the hook + query key so an Infinity-stale shallow result can't serve a deeper request. |
| M9 | `api/mistakes.py` | Clearing both classification fields now resets `classified_at`, returning the row to the unclassified queue (regression test added). |
| M10 | `Makefile` | `clean` removes rebuildable artifacts only; the DB moved to a separate `clean-db` target with a typed-"yes" confirmation. |

(Also, from the Phase-12 verification findings: the Dashboard's "Mistake types" chart now shows a "nothing classified yet" hint instead of an empty plot on a fresh database.)

---

## 3. Spec-conformance gaps

1. ~~**"Needs Lichess analysis" re-fetch workflow is broken.**~~ **FIXED 2026-07-06** (implements F2): `fetch_game_by_id` implemented in both sources (protocol signature now `(user, game_id) -> GameRecord | None` — the original couldn't resolve `user_color`; DESIGN.md updated), plus `refresh_game` service and `POST /games/{id}/refresh`. Refresh updates PGN/`has_evals`/metadata in place and clears `analyzed_at` only when the PGN changed; upstream 404 → 404, user-no-longer-a-player → 409, other upstream errors → 502. Also un-freezes grown study chapters. UI affordance (refresh action on the "Needs Lichess analysis" pill + Lichess deep link) remains a Phase 12 item.
2. ~~**Phase 12 outstanding (expected).**~~ **DONE 2026-07-07:** settings page wired to GET/PATCH /settings (username read-only by design) with re-analysis warning + "Re-analyze all" surfacing the reconcile counters; Games page import / analyze-pending controls and per-row Refresh + Lichess deep link; FastAPI serves `frontend/dist/` at `/` with SPA fallback when built; HOWTO.md added; README rewritten with the usage workflow. Still deliberately absent: `GET /games/import/status/{job_id}` (ingestion is synchronous — becomes relevant with the job-model concern in §4.1).
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
- **F4 — Filtered analytics: DONE 2026-07-07.** Shared `StatFilters` dependency (`from`/`to`, `source`, `color`, `severity`, `speed`) on all three `/stats/*` endpoints; `speed` is bucketed from the TimeControl header (new `chess_utils/time_control.py`, Lichess convention — `parse_time_control` moved there from `services/analysis.py`). Filter bar on /stats with state in the URL; Dashboard intentionally stays unfiltered.
- **F5 — Drill mode** (from the existing backlog): re-present classified mistake positions as find-the-move puzzles ordered by weakest Layer A × B cell, spaced repetition on misses. Closes the diagnosis → training loop; today the prescription is text-only.
- **F6 — Smaller:** import/analyze buttons in the UI (Phase 12); honor `#ply=` in GameDetail (M1); "heuristic accuracy" stat (suggested-vs-classified agreement rate over time); per-game eval graph in review (data already in `positions`); CSV/PDF export of classified mistakes for a coach.

---

## 6. Suggested order of work

1. ~~B1 / F1 (classification-preserving re-analysis)~~ **DONE 2026-07-06.**
2. ~~B2 (FEN-start parity)~~ **DONE 2026-07-06.**
3. ~~B4 (settings → study source wiring)~~ **DONE 2026-07-06** — the Phase 12 settings UI can now build on it.
4. ~~F2 (game refresh)~~ **DONE 2026-07-06.**
5. ~~B3~~ **DONE 2026-07-07**; ~~Phase 12 UI~~ **DONE 2026-07-07**; ~~minor bugs M1–M10~~ **ALL DONE 2026-07-07**.
6. ~~F4 (filtered analytics)~~ **DONE 2026-07-07**. F3 → F5 as feature work — **the only items left from this review**.

## 7. Verification notes for the next agent

- Repro for B2/B3 (run with `uv run python`): parse a PGN through `backend.app.analyzers.lichess_pgn.parse_pgn_for_positions`, then call `backend.app.services.analysis.is_user_move` (B2) or `backend.app.chess_utils.winrate.winrate_for_color` on a `[%eval #-0]` final ply (B3).
- The dev server is started by the user in their own terminal — don't background it.
- `uv run pytest` from repo root; pytest config lives in `pyproject.toml` (`testpaths = backend/tests`, asyncio auto mode).
