from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.analysis import router as analysis_router
from backend.app.api.games import router as games_router
from backend.app.api.mistakes import router as mistakes_router
from backend.app.api.settings import router as settings_router
from backend.app.api.stats import router as stats_router

API_V1_PREFIX = "/api/v1"

app = FastAPI(title="Chess Mistake Tracker", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games_router, prefix=API_V1_PREFIX)
app.include_router(mistakes_router, prefix=API_V1_PREFIX)
app.include_router(stats_router, prefix=API_V1_PREFIX)
app.include_router(settings_router, prefix=API_V1_PREFIX)
app.include_router(analysis_router, prefix=API_V1_PREFIX)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class _SpaStaticFiles(StaticFiles):
    """Static files with SPA fallback: unknown paths serve index.html so
    client-side routes (/games/3, /mistakes/7…) survive a hard reload.
    Starlette signals a missing file by *raising* its HTTPException (not by
    returning a 404 response) — and it must be caught as the Starlette class:
    FastAPI's HTTPException is a subclass, which would silently not match."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404:
                raise
            # Only extensionless, non-API paths read as client-side routes.
            # A typo'd /api/... must stay a 404, and a missing asset file
            # should fail loudly rather than come back as HTML.
            if path.startswith("api/") or "." in path.rsplit("/", 1)[-1]:
                raise
            return await super().get_response("index.html", scope)


# Production-style local serve (DESIGN.md §"Packaging & Deployment"): when the
# frontend has been built (`cd frontend && npm run build`), serve it at `/` so
# one uvicorn process is the whole app. Registered after the routers, so
# /api/v1/* , /health and /docs always win. In dev (no dist/) this is skipped
# and Vite serves the frontend with a proxy instead.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", _SpaStaticFiles(directory=_dist, html=True), name="frontend")
