# Chess Mistake Tracker

A personal chess analysis tool that ingests games from Lichess (online games and studies) and chess.com, identifies positions where the user's evaluation drops significantly, and supports a structured classification workflow for diagnosing recurring mistake patterns.

## Why

For a club player who consistently builds opening advantages but gives them back in the middlegame and endgame, the path to improvement runs through pattern-finding: which kinds of mistakes recur, in which kinds of positions, under which conditions. Generic engine analysis tells you *what* the right move was; it doesn't tell you *why* you didn't play it. This tool adds the missing classification layer.

## Classification System

Two orthogonal layers, plus situational tags. Based on Dalton Perrine's [4-question framework](https://chesschatter.substack.com/p/chess-thinking-process), which itself builds on Nick Vasquez's "Got It Wrong vs Didn't See It" distinction.

### Layer A — Which thinking step failed?

1. **Step 1: Read opponent's move.** Failed to see what their last move threatened or accomplished.
2. **Step 2: Find forcing moves.** Missed an available check / capture / threat / tactic of your own.
3. **Step 3: Improve the position.** In a quiet position with no tactics, chose the wrong plan / wrong piece / missed prophylaxis.
4. **Step 4: Blunder check.** Played a move without considering opponent's forcing reply.

### Layer B — Awareness

- **Got It Wrong** — saw the idea, calculated or evaluated it incorrectly.
- **Didn't See It** — total blind spot; the idea never entered consideration.

### Layer C — Situational tags

- `time_pressure` — flagged automatically when move was played fast relative to baseline or under a clock threshold.
- `low_material` — endgame.
- `transition` — pawn structure change, king safety change, queens-off, etc.
- Free-form notes.

This produces an 8-cell Layer A × Layer B matrix. Each cell maps to a different training prescription (e.g., Step 4/Didn't See → blunder-check habit drilling; Step 2/Got It Wrong → calculation training; Step 3/Got It Wrong → positional judgment).

## High-Level Architecture

API-first. Backend is the source of truth and exposes a documented HTTP API. The web frontend is one consumer; future iOS, Electron, or CLI consumers would plug into the same API. All external dependencies (game source, engine) are abstracted behind interfaces — that's how chess.com support and local Stockfish were added without disturbing the rest of the system.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite
- **Chess logic:** `python-chess`
- **Frontend:** React + Vite + TypeScript
- **Board UI:** `chessground` (Lichess's board library)
- **Charts:** Recharts
- **Packaging:** `uv` for Python (project-local `.venv`, no system pollution); `.nvmrc` for Node version pinning. A `Makefile` wraps the common commands. Optional Docker Compose path for true portability.
- **Deployment:** Local-first. Optional Railway/Fly.io path documented for future remote use.

## Project Status

Built and in daily use (Phases 1–12 of the implementation plan complete; Docker packaging is the only optional phase remaining). See:
- [DESIGN.md](./DESIGN.md) — architecture, data model, classification logic, heuristics
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — phased build plan (history + backlog)
- [HOWTO.md](./HOWTO.md) — how to use the classification system day to day
- [CODE_REVIEW.md](./CODE_REVIEW.md) — 2026-07-06 review findings and their status

## Setup

This project is **strictly self-contained**: nothing it installs touches system Python or system Node. Python lives in a project-local `.venv/` managed by `uv`; Node is selected by `nvm` / `fnm` from `~/`.

### Prerequisites (one-time, per machine)

- **`uv`** — Python package + environment manager. Installs into `~/.local/bin`:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **`nvm`** or **`fnm`** — per-user Node version manager. Either is fine. Install instructions: <https://github.com/nvm-sh/nvm> or <https://github.com/Schniz/fnm>.

### First-time project setup

```bash
git clone <this repo>
cd chess-mistake-tracker

cp .env.example .env          # then edit .env: set LICHESS_USERNAME at minimum
nvm use                       # or: fnm use   — reads .nvmrc (Node 20)

make install                  # creates ./.venv via `uv sync`; npm ci for the frontend
make migrate                  # applies Alembic migrations → ./data/chess.db
make seed                     # creates the single user from LICHESS_USERNAME (idempotent)
make dev                      # runs backend (:8000) and frontend (:5173) together
```

The app is at <http://localhost:5173>; the backend serves on <http://localhost:8000>. Health check: `curl localhost:8000/health`. OpenAPI docs: <http://localhost:8000/docs>.

Optional (recommended): install [Stockfish](https://stockfishchess.org/) (`apt install stockfish`, or set `STOCKFISH_PATH`) to enable analyzing games that carry no Lichess evals (OTB study chapters, unanalyzed online games), the interactive Explore board, and higher-quality best-move suggestions. Without it those features degrade gracefully (eval-less games need Lichess's "request analysis" flow; cloud-eval fallback / hidden panel elsewhere). The Settings page shows whether the engine was found.

## Using the app

The daily loop, all reachable from the UI:

1. **Import** — on the *Games* page pick "Lichess games" (with a max), "Lichess studies", or "chess.com games" and click Import. Study IDs, the player aliases used to match your name in OTB chapters, and your chess.com username are edited on the *Settings* page (the `LICHESS_STUDY_IDS` / `STUDY_PLAYER_ALIASES` / `CHESSCOM_USERNAME` env vars only seed them on first run). Re-importing is idempotent — existing games are skipped, never overwritten. chess.com PGNs never carry engine evals, so analyzing those games requires local Stockfish.
2. **Analyze** — "Analyze pending" processes every analyzable game: positions, mistake detection, and a suggested thinking-step per mistake. Games whose PGN carries `%eval` annotations use those; with local Stockfish installed, games without evals (OTB study chapters, unanalyzed online games) are evaluated locally — expect a few seconds per game.
3. **Without Stockfish**, eval-less games show a *Needs Lichess analysis* status instead: click *Request ↗* to open the game on Lichess and request computer analysis there, then click *Refresh* to re-fetch it — the game becomes analyzable. (Both paths remain available when the engine is installed; Lichess's server analysis is deeper than the local default.)
4. **Classify** — the *Mistakes* page is the queue. Each mistake gets a thinking step (1–4), an awareness call (*Got it wrong* / *Didn't see it*), optional tags and notes. Keyboard-first: `1–4`, `G`/`D`, `Enter` to save-and-advance. See [HOWTO.md](./HOWTO.md) for what the buckets mean.
5. **Review patterns** — the *Dashboard* and *Stats* pages show where your mistakes cluster and what to train first. The Stats page has a filter bar (date range, source, color, severity, speed) for slicing — e.g. blitz-only vs OTB-only to see whether the patterns differ.
6. **Tune** — detection thresholds and suppression bounds live on the *Settings* page. After changing them, use the offered "Re-analyze all games" — classifications and notes always survive re-analysis.

### Common commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` + `npm ci` (frontend, when present) |
| `make dev` | Backend (and frontend, once present) with hot reload |
| `make backend` | Backend only |
| `make test` | `pytest` (and frontend tests, once present) |
| `make migrate` | `alembic upgrade head` |
| `make seed` | Idempotently create the configured user |
| `make clean` | Remove rebuildable artifacts (`.venv`, `node_modules`, `frontend/dist`) |
| `make clean-db` | Delete the SQLite DB — asks for confirmation; classifications are unrecoverable |

All Python invocations go through `uv run` (directly or via `make`); never use bare `pip` or `python` against this project.

### Production-style serve (single process)

```bash
cd frontend && npm run build     # static assets → frontend/dist/
make backend                     # FastAPI now also serves the UI at :8000
```

When `frontend/dist/` exists, the backend serves the built app at <http://localhost:8000> — one process, one port. `make dev` (Vite + hot reload) remains the development workflow.
