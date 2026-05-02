# Chess Mistake Tracker

A personal chess analysis tool that ingests games from Lichess (online games and studies), identifies positions where the user's evaluation drops significantly, and supports a structured classification workflow for diagnosing recurring mistake patterns.

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

API-first. Backend is the source of truth and exposes a documented HTTP API. The web frontend is one consumer; future iOS, Electron, or CLI consumers would plug into the same API. All external dependencies (game source, engine) are abstracted behind interfaces so chess.com support and local Stockfish can be added without disturbing the rest of the system.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy, SQLite
- **Chess logic:** `python-chess`
- **Frontend:** React + Vite + TypeScript
- **Board UI:** `chessground` (Lichess's board library)
- **Charts:** Recharts
- **Packaging:** `uv` for Python (project-local `.venv`, no system pollution); `.nvmrc` for Node version pinning. A `Makefile` wraps the common commands. Optional Docker Compose path for true portability.
- **Deployment:** Local-first. Optional Railway/Fly.io path documented for future remote use.

## Project Status

Planning. See:
- [DESIGN.md](./DESIGN.md) — architecture, data model, classification logic, heuristics
- [IMPLEMENTATION.md](./IMPLEMENTATION.md) — phased build plan for Claude Code

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

make install                  # creates ./.venv via `uv sync`; npm ci once frontend exists
make migrate                  # applies Alembic migrations → ./data/chess.db
make seed                     # creates the single user from LICHESS_USERNAME (idempotent)
make dev                      # runs the backend (and frontend, once Phase 8 lands)
```

The backend serves on <http://localhost:8000>. Health check: `curl localhost:8000/health`. OpenAPI docs: <http://localhost:8000/docs>.

### Common commands

| Command | What it does |
|---|---|
| `make install` | `uv sync` + `npm ci` (frontend, when present) |
| `make dev` | Backend (and frontend, once present) with hot reload |
| `make backend` | Backend only |
| `make test` | `pytest` (and frontend tests, once present) |
| `make migrate` | `alembic upgrade head` |
| `make seed` | Idempotently create the configured user |
| `make clean` | Remove `.venv`, `node_modules`, and the SQLite DB |

All Python invocations go through `uv run` (directly or via `make`); never use bare `pip` or `python` against this project.
