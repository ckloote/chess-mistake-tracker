# Design Document

## Goals

1. Ingest the user's Lichess games (online play) and Lichess studies (where OTB games are stored).
2. For each game, identify positions where the user's win% dropped by a configurable threshold ("mistakes").
3. Suggest a likely Layer A bucket for each mistake using engine + position heuristics.
4. Provide a review UI for the user to confirm/override the Layer A suggestion and assign Layer B (Got It Wrong / Didn't See It) plus situational tags.
5. Provide aggregate analytics so the user can see which buckets dominate their mistake distribution and target training accordingly.

## Non-Goals (MVP)

- chess.com support (planned post-MVP; sources are abstracted to enable it).
- Local engine analysis (planned post-MVP; analyzers are abstracted to enable it).
- Multi-user support (single-user only; data model leaves room).
- Mobile-native UI (API is designed to support it later).
- Coaching recommendations beyond bucket-level prescriptions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Frontend (React)                       │
│   Dashboard · Game List · Game Review · Classification UI    │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/JSON
┌────────────────────────────▼────────────────────────────────┐
│                      FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Ingestion│  │ Analysis │  │   Mistake    │  │   API   │ │
│  │ Service  │  │ Service  │  │  Detector +  │  │ Routes  │ │
│  │          │  │          │  │  Classifier  │  │         │ │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  └────┬────┘ │
│       │             │               │                │      │
│  ┌────▼─────────────▼───────────────▼────────────────▼───┐ │
│  │              SQLAlchemy ORM · SQLite                  │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
       │                    │
┌──────▼──────┐      ┌─────▼─────────┐
│ GameSource  │      │   Analyzer    │
│ (interface) │      │  (interface)  │
├─────────────┤      ├───────────────┤
│ Lichess     │      │ Lichess PGN   │
│ Lichess     │      │ eval parser   │
│  Study      │      │ (cloud eval   │
│ [chess.com] │      │  fallback)    │
└─────────────┘      │ [Stockfish]   │
                     └───────────────┘
```

`GameSource` and `Analyzer` are protocol classes. MVP ships one implementation each. New sources/analyzers are added by implementing the protocol and registering the implementation; nothing else changes.

## Tech Stack & Rationale

| Layer | Choice | Why |
|---|---|---|
| Backend lang | Python 3.11+ | `python-chess` is the standard library and only exists for Python; FastAPI is excellent. |
| Web framework | FastAPI | Type hints → auto-generated OpenAPI docs that the React app and any future iOS/Electron client can use. Async support for parallel Lichess fetches. |
| ORM | SQLAlchemy 2.0 | Migrations via Alembic. Easy switch to Postgres later if we ever want to host. |
| DB | SQLite | Single-user, local-first. Zero ops. File-on-disk is the right answer. |
| Chess core | `python-chess` | PGN parsing, FEN, legal move generation, board representation. |
| Frontend | React + Vite + TypeScript | Mature ecosystem; chessground is JS; types catch a class of dumb bugs early. |
| Board widget | chessground | Lichess's own board. Pairs naturally with PGN data from Lichess. |
| Charts | Recharts | React-native, sufficient for the analytics views. |
| Tests | pytest, Vitest | Standard. |

## Data Model

### `users`
Single row in MVP, but the schema is multi-user-safe.

| col | type | notes |
|---|---|---|
| id | int PK | |
| lichess_username | text unique | required |
| chesscom_username | text nullable | for future |
| created_at | timestamp | |

### `games`
One row per unique game ingested.

| col | type | notes |
|---|---|---|
| id | int PK | |
| user_id | int FK | |
| source | text | `lichess_online`, `lichess_study` (future: `chesscom`) |
| source_game_id | text | Lichess game ID, or `studyId:chapterId` |
| user_color | text | `white` or `black` |
| white | text | name |
| black | text | name |
| white_elo | int nullable | |
| black_elo | int nullable | |
| result | text | `1-0`, `0-1`, `1/2-1/2`, `*` |
| time_control | text | e.g. `600+5`, `5400+30`, or `OTB` |
| played_at | timestamp | |
| pgn | text | full PGN, source of truth |
| has_evals | bool | true if PGN contained `%eval` annotations |
| analyzed_at | timestamp nullable | when our analyzer ran on it |
| ingested_at | timestamp | |

Unique on (`user_id`, `source`, `source_game_id`).

### `positions`
One row per ply. Generated when a game is analyzed. Lazy: only created on first analysis.

| col | type | notes |
|---|---|---|
| id | int PK | |
| game_id | int FK | |
| ply | int | 0 = starting position |
| fen | text | |
| san | text nullable | move that produced this position (null for ply 0) |
| uci | text nullable | |
| is_user_move | bool | did the user play the move that led here |
| eval_cp | int nullable | from white's perspective; null if mate |
| mate_in | int nullable | + = white mates, − = black mates |
| clock_ms | int nullable | seconds remaining after this move was played |
| time_spent_ms | int nullable | computed from clock deltas |

Index on (`game_id`, `ply`).

### `mistakes`
One row per detected mistake. Created during analysis after `positions` are populated.

| col | type | notes |
|---|---|---|
| id | int PK | |
| game_id | int FK | |
| ply | int | the ply where the user moved |
| severity | text | `inaccuracy`, `mistake`, `blunder` |
| eval_before_cp | int | win%-equivalent eval before user's move |
| eval_after_cp | int | after user's move |
| winrate_before | float | 0–100 |
| winrate_after | float | 0–100 |
| winrate_drop | float | always positive |
| best_move_uci | text nullable | engine's preferred move from `eval_before` position |
| best_move_san | text nullable | |
| suggested_step | int nullable | 1–4, heuristic suggestion |
| suggestion_confidence | float nullable | 0–1, how sure the heuristic is |
| classified_step | int nullable | 1–4, user's choice |
| classified_awareness | text nullable | `got_it_wrong` or `didnt_see_it` |
| time_pressure_flag | bool | auto-set during detection |
| transition_flag | bool | auto-set heuristically (queens off, big structural change, etc.) |
| endgame_flag | bool | auto-set when material below threshold |
| user_notes | text nullable | |
| classified_at | timestamp nullable | |

Unique on (`game_id`, `ply`).

## Mistake Detection

### Win% from centipawn eval

```python
import math

def cp_to_winrate(cp: int) -> float:
    """Win% from white's perspective. cp clamped to [-1000, 1000]."""
    cp = max(-1000, min(1000, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)
```

For mate scores, use ±1000 cp equivalent (winrate ≈ 100 / 0). Document this approximation; it doesn't matter for our purposes since mate positions aren't where the user is "giving away an advantage."

### Detection algorithm

For each user move (ply where `is_user_move` is true):

1. Compute `winrate_before` from `eval_cp` of the position the user moved from, **from the user's color's perspective**.
2. Compute `winrate_after` from `eval_cp` of the position the user's move produced, also from the user's color's perspective.
3. `winrate_drop = winrate_before - winrate_after`. If positive, classify:
   - `winrate_drop ≥ 20` → blunder
   - `winrate_drop ≥ 10` → mistake
   - `winrate_drop ≥ 5` → inaccuracy
   - else → not a mistake
4. Suppress if `winrate_before < 30` and `winrate_after < 30` (already losing; not "giving away an advantage" — out of scope for the user's stated focus). Make this configurable.
5. Suppress if `winrate_before > 90` and `winrate_after > 80` (still very much winning despite imprecision). Configurable.

The 30/90 suppression rules implement the user's actual concern ("I make mistakes that *cost* me the advantage") rather than logging every imperfect move. Both thresholds are tunable from a settings page.

### Time-pressure flag

For each user move, compute `time_spent_ms` from the clock deltas in the PGN. Flag the move as time-pressure-influenced if any of:
- `time_spent_ms < 5000` (under 5 seconds in any time control)
- `clock_ms < 60000` for 10+0-style games, scaled appropriately for longer time controls
- The move was at least 3× faster than the user's median move time in that game

These thresholds are configurable.

## Layer A Heuristic Suggestion

For each detected mistake, suggest one of Steps 1–4 plus a confidence score. The user can accept or override. The heuristic reads: position before user's move (`P_before`), opponent's previous move (`M_opp`), engine's best move from `P_before` (`M_best`), user's actual move (`M_user`), position after user's move (`P_after`), and engine's best response from `P_after` (`M_opp_response`).

### Step 4 — failed blunder check (highest priority)

Triggers: `M_user` looked locally reasonable but `M_opp_response` is forcing (check or capture) AND wins material or causes a large eval swing.

Rule: if `M_opp_response` from `P_after` is a check or a capture, AND the eval after `M_opp_response` is ≥ 200cp worse for the user than the eval after `M_user`, suggest **Step 4** with confidence ≈ 0.8.

### Step 2 — missed forcing move

Triggers: a forcing move was available in `P_before` that the user didn't play.

Rule: if `M_best` from `P_before` is a check, capture, or creates an immediate mate/material threat, AND `M_user` was non-forcing, AND `winrate_before` was already ≥ 50, suggest **Step 2** with confidence ≈ 0.7. Detecting "creates a mate threat" is harder; for MVP it's sufficient to detect check-or-capture and tag this as Step 2.

### Step 1 — missed opponent's threat

Triggers: opponent's previous move created a threat the user failed to address.

Rule: if `M_best` from `P_before` defends a piece that becomes attackable, blocks a check, evades a fork, or otherwise responds to a tactical motif introduced by `M_opp`, suggest **Step 1**. Detecting "responds to a threat introduced by opponent" reliably is the hardest of the four. MVP implementation:
- After `M_opp`, run engine for 1 ply: does opponent have a tactical follow-up (check, winning capture, mating attack) if user passes (i.e., make a null move and see if opponent's eval jumps)?
- If yes, AND `M_best` from `P_before` neutralizes that follow-up, AND `M_user` doesn't, suggest **Step 1** with confidence ≈ 0.6.

### Step 3 — strategic inaccuracy (default)

Triggers: quiet position, no forcing moves for either side, modest win% drop.

Rule: if none of Steps 1, 2, or 4 fire, suggest **Step 3** with confidence ≈ 0.5.

### Tie-breaking

Steps 4 → 2 → 1 → 3 in priority. If multiple fire, the highest-priority one wins, but record all that fired in a `suggestion_debug` JSON field for transparency in the UI.

### What the heuristic deliberately doesn't try to do

It does not attempt Layer B. "Got It Wrong vs Didn't See It" is genuinely introspective and the user is the only one who knows. The UI shows the suggestion as a starting point with a one-click accept and an explicit override.

## Source Abstractions

### `GameSource` protocol

```python
class GameSource(Protocol):
    name: str  # e.g. "lichess_online"

    async def fetch_recent_games(
        self, user: User, since: datetime | None = None, limit: int | None = None
    ) -> AsyncIterator[GameRecord]: ...

    async def fetch_game_by_id(self, game_id: str) -> GameRecord: ...
```

`GameRecord` is a dataclass with: `source`, `source_game_id`, `pgn`, plus parsed metadata (white/black/result/etc.). PGN is the canonical form; metadata is convenience cache.

### MVP implementations

- `LichessOnlineSource`: hits `GET /api/games/user/{username}?evals=true&clocks=true&pgnInJson=false&max=N`. Streams NDJSON or PGN.
- `LichessStudySource`: takes a list of study IDs (configured per user), fetches `GET /api/study/{id}.pgn`, splits into chapters, and emits one `GameRecord` per chapter where the user is a player.

### Future implementations

- `ChessComSource`: hits chess.com's monthly archives API.
- The interface assumption "PGN is the canonical form" should hold for chess.com.

## Engine / Analyzer Abstractions

### `Analyzer` protocol

```python
class Analyzer(Protocol):
    name: str

    async def analyze_position(self, fen: str, multipv: int = 1) -> list[EvalResult]: ...
    async def analyze_game(self, pgn: str) -> list[PositionEval]: ...
    @property
    def supports_per_position(self) -> bool: ...
```

`EvalResult` carries: `cp`, `mate`, `pv` (principal variation as UCI list), `depth`. `PositionEval` is one per ply.

### MVP implementations

- `LichessPgnEvalAnalyzer`: parses `%eval` annotations from PGNs that already have Lichess computer analysis. No network call. Most efficient.
- `LichessCloudEvalAnalyzer`: hits `POST /api/cloud-eval` for individual positions when needed (e.g., to compute heuristic side-checks like "what's the eval after a null move"). Cloud doesn't have all positions; gracefully returns null.

### Future implementations

- `StockfishLocalAnalyzer`: spawns local Stockfish via `python-chess.engine`. Configurable depth/time/multipv. Becomes the canonical analyzer; cloud fallback for speed.

### Practical note on MVP coverage

Lichess's PGN export only embeds evals if computer analysis has been requested for the game. The user already has the muscle memory for clicking "request analysis" on important games. The tool will:
1. On ingestion, mark `has_evals` true/false from the PGN.
2. Process `has_evals=true` games immediately.
3. List `has_evals=false` games in a "needs Lichess analysis" section, with a deep link to each game on Lichess so the user can request analysis there. After a re-fetch, the game becomes processable.
4. Document Stockfish-local as the v1.1 unblocker.

## API Surface

All endpoints under `/api/v1`. JSON in/out. OpenAPI docs auto-generated by FastAPI.

### Ingestion

- `POST /games/import` — body: `{ source, since?, limit? }`. Triggers ingestion run. Returns counts.
- `GET /games/import/status/{job_id}` — polling endpoint if ingestion is async.

### Games

- `GET /games` — query: `source`, `from`, `to`, `result`, `color`, `analyzed_only`, `has_mistakes`, `page`, `page_size`. Returns paginated list.
- `GET /games/{id}` — full game with positions and mistakes.
- `POST /games/{id}/analyze` — runs analysis pipeline for one game (mistake detection + heuristic suggestions). Idempotent.
- `POST /games/analyze-pending` — runs analysis on all unprocessed `has_evals=true` games.

### Mistakes

- `GET /mistakes` — query: `step`, `awareness`, `severity`, `time_pressure`, `unclassified_only`, `from`, `to`. Returns paginated list with game context.
- `GET /mistakes/{id}` — full mistake including FEN, best line, suggestion debug.
- `PATCH /mistakes/{id}` — body: `{ classified_step?, classified_awareness?, user_notes? }`. Saves classification.

### Analytics

- `GET /stats/summary` — counts by step, by awareness, by severity, total mistakes, classified vs unclassified.
- `GET /stats/breakdown` — query: `by` (one of `step`, `awareness`, `step_x_awareness`, `phase`, `time_pressure`, `month`). Returns counts and trend lines.
- `GET /stats/training-prescription` — returns ranked list of weakest cells (e.g., "Step 4 / Didn't See It is your most common pattern: 32% of your blunders") with bucket-specific suggestions.

### Settings

- `GET /settings`, `PATCH /settings` — thresholds, suppression rules, study IDs.

## Frontend

### Pages

- **/** Dashboard: recent games, top mistake patterns, quick links to unclassified mistakes.
- **/games**: filterable list. Click → review.
- **/games/:id**: chessground board on the left, move list on the right with mistakes highlighted, mistake detail panel below.
- **/mistakes**: cross-game mistake list, primarily for catching up on classification.
- **/mistakes/:id**: full classification UI with board, best line, suggestion, accept/override controls.
- **/stats**: charts. Step distribution, awareness distribution, time series, time-pressure correlation.
- **/settings**: thresholds, Lichess username, study IDs.

### State / data fetching

TanStack Query (React Query) for server state. Local UI state via React hooks. No global store needed at this scale.

### Classification UI specifics

The single most important UI in the app. For each mistake:
- Board at the position before the user's move, with the user's move and the engine's best move both shown as arrows.
- One-click button per Layer A bucket. The suggested step is pre-selected and visually distinct.
- Two buttons for Layer B: Got It Wrong / Didn't See It.
- Auto-flagged tags shown as already-on chips (time_pressure, endgame, transition); user-toggleable.
- Free-text notes field.
- Save advances to next unclassified mistake. Keyboard shortcuts: 1/2/3/4 for step, G/D for awareness, Enter to save+next, Esc to cancel.

## Packaging & Deployment

### Principles

- **No system pollution.** Nothing the project depends on installs to system-wide Python or system-wide Node. Both stacks live entirely in the project directory or in a per-project version manager.
- **Reproducibility.** Lockfiles for both Python and JavaScript dependencies are checked in. A fresh clone produces an identical environment.
- **Single-machine MVP, portable later.** The MVP runs natively for dev speed. A Docker Compose path exists as a documented escape hatch for true portability (different machine, home server, etc.) without becoming the primary workflow.

### Python: `uv` + project-local virtualenv

`uv` is the package and environment manager. It is fast, creates a project-local `.venv/` directory, and reads from a single `pyproject.toml` plus a checked-in `uv.lock`.

Setup workflow on any machine:

```bash
# install uv once per machine, into the user's home, not system Python
curl -LsSf https://astral.sh/uv/install.sh | sh

# from the project root
uv sync          # creates ./.venv and installs everything from uv.lock
uv run pytest    # runs commands inside the venv without needing manual activation
```

The `.venv/` directory is gitignored. The `uv.lock` is checked in. `pyproject.toml` declares dependencies with version ranges; `uv.lock` pins exact versions. `uv` is installed once per machine into `~/.local/bin` and is not a system package.

Why `uv` over alternatives:
- vs. `pip` + `venv`: ergonomically the same idea but `uv` is dramatically faster, has built-in lockfile support, and handles Python version pinning if needed.
- vs. Poetry: simpler, faster, broadly the new default for greenfield Python projects.
- vs. Conda: heavyweight, designed for scientific computing's binary-dependency hell, overkill here.

### Node: `.nvmrc` + project-local `node_modules`

Node modules already install to `node_modules/` by default — local by construction. The Node runtime version is the only thing that risks polluting the system. The fix is a per-user version manager:

```bash
# .nvmrc in the project root pins the Node version
echo "20" > .nvmrc

# developer uses nvm or fnm to activate
nvm use            # reads .nvmrc, switches to that version for this shell
# or with fnm:
fnm use
```

`nvm` and `fnm` are user-level tools that install into the home directory; they do not touch system Node. The README documents that either is acceptable. `package.json` declares the Node engine range explicitly:

```json
"engines": { "node": ">=20.0.0 <21.0.0" }
```

`package-lock.json` is checked in for reproducibility.

### A Makefile for the common commands

A top-level `Makefile` wraps the tedium so the developer never has to remember `uv run uvicorn backend.app.main:app --reload`:

```make
.PHONY: install dev backend frontend test migrate seed clean

install:
	uv sync
	cd frontend && npm ci

dev:
	# runs backend and frontend concurrently
	$(MAKE) -j 2 backend frontend

backend:
	uv run uvicorn backend.app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	uv run pytest backend/tests
	cd frontend && npm test

migrate:
	uv run alembic upgrade head

seed:
	uv run python scripts/seed.py

clean:
	rm -rf .venv frontend/node_modules data/*.db
```

### Production-style local serve

For "running it for real" on the dev machine without hot reload:

```bash
cd frontend && npm run build       # static assets to frontend/dist/
uv run uvicorn backend.app.main:app --port 8000
```

FastAPI serves the built frontend's `dist/` as static files at `/`, with API routes at `/api/v1/*`. One process, one port, the whole app available at `http://localhost:8000`.

### Optional: Docker Compose path

A `docker-compose.yml` and `Dockerfile` live in the repo as a documented secondary path, not the primary workflow. The Dockerfile uses a multi-stage build: stage 1 builds the frontend, stage 2 sets up the Python env, final image copies the frontend `dist/` into the Python image and runs uvicorn. The compose file mounts `./data` as a volume so the SQLite DB persists across container rebuilds.

```bash
docker compose up --build
```

This path is for: running on a different machine without installing uv/nvm, running on a home server, or any future remote deployment. It is **not** the daily dev loop.

### Data directory

SQLite database lives at `./data/chess.db`. The `data/` directory is gitignored. Application code reads the path from config (`CHESS_DB_PATH` env var, default `./data/chess.db`), so it can be relocated for backup or for testing without code changes.

### Hosted deployment (deferred)

If/when remote hosting is desired, Railway remains the lightweight option (consistent with the user's prior research on Python web app hosting). The Docker Compose setup transfers naturally to Railway, Fly.io, or any container host. SQLite ports cleanly to Postgres via SQLAlchemy if scale ever justifies it.

## Open Questions

1. **Chapter-to-game matching for studies.** A study can contain games where the user is white, black, or neither (analysis of pro games, etc.). MVP: detect by matching the configured Lichess username — or any name in the comma-separated `STUDY_PLAYER_ALIASES` env var (case-insensitive) — against the White/Black PGN tags. The alias list is the practical stopgap for OTB studies, where the user is typically recorded by initials or real name rather than Lichess handle. Chapters with no match are skipped and logged at WARNING level. A fuller "prompt during ingestion to confirm color or skip" flow is post-MVP and depends on the Phase 10 classification UI.
2. **Time pressure for OTB.** No clock data. Time pressure flag will simply not fire for OTB games. Future: optional manual entry of time-on-clock per move during PGN import.
3. **Multi-game training mode (post-MVP).** Re-present positions where the user previously made mistakes as a "drill" — same position, see if you find the right move now. Useful, deferred.
