from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.games import router as games_router
from backend.app.api.mistakes import router as mistakes_router

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
