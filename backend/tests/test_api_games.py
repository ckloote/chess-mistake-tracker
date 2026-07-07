from datetime import datetime, timezone

from backend.tests.conftest import make_game, make_mistake, make_position, make_user


def test_list_games_default_returns_empty_paginated_envelope(client) -> None:
    response = client.get("/api/v1/games")
    assert response.status_code == 200
    data = response.json()
    assert data == {"total": 0, "page": 1, "page_size": 50, "items": []}


def test_list_games_filters_by_source(client, db) -> None:
    user = make_user(db)
    make_game(db, user, source="lichess_online", source_game_id="o0000001")
    make_game(db, user, source="lichess_study", source_game_id="study:chap0001")

    online = client.get("/api/v1/games?source=lichess_online").json()
    assert online["total"] == 1
    assert online["items"][0]["source"] == "lichess_online"

    study = client.get("/api/v1/games?source=lichess_study").json()
    assert study["total"] == 1
    assert study["items"][0]["source"] == "lichess_study"


def test_list_games_filters_by_color_and_result(client, db) -> None:
    user = make_user(db)
    make_game(db, user, source_game_id="g0000001", user_color="white", result="1-0")
    make_game(db, user, source_game_id="g0000002", user_color="black", result="0-1")

    white_only = client.get("/api/v1/games?color=white").json()
    assert white_only["total"] == 1
    assert white_only["items"][0]["user_color"] == "white"

    losses = client.get("/api/v1/games?result=0-1").json()
    assert losses["total"] == 1


def test_list_games_filters_by_date_range(client, db) -> None:
    user = make_user(db)
    make_game(
        db, user, source_game_id="g0000010",
        played_at=datetime(2025, 5, 1, tzinfo=timezone.utc),
    )
    make_game(
        db, user, source_game_id="g0000011",
        played_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
    )

    may_only = client.get("/api/v1/games?from=2025-05-01&to=2025-05-31").json()
    assert may_only["total"] == 1
    assert may_only["items"][0]["source_game_id"] == "g0000010"


def test_list_games_filters_by_analyzed_only(client, db) -> None:
    user = make_user(db)
    make_game(db, user, source_game_id="g0000020", analyzed=False)
    make_game(db, user, source_game_id="g0000021", analyzed=True)

    analyzed = client.get("/api/v1/games?analyzed_only=true").json()
    assert analyzed["total"] == 1
    assert analyzed["items"][0]["analyzed_at"] is not None


def test_list_games_filters_by_has_mistakes(client, db) -> None:
    user = make_user(db)
    clean = make_game(db, user, source_game_id="g0000030")
    mistaken = make_game(db, user, source_game_id="g0000031")
    make_mistake(db, mistaken)

    with_mistakes = client.get("/api/v1/games?has_mistakes=true").json()
    assert with_mistakes["total"] == 1
    assert with_mistakes["items"][0]["id"] == mistaken.id

    without = client.get("/api/v1/games?has_mistakes=false").json()
    assert without["total"] == 1
    assert without["items"][0]["id"] == clean.id


def test_list_games_paginates(client, db) -> None:
    user = make_user(db)
    for i in range(5):
        make_game(db, user, source_game_id=f"g{i:07d}")

    page = client.get("/api/v1/games?page=1&page_size=2").json()
    assert page["total"] == 5
    assert page["page"] == 1
    assert page["page_size"] == 2
    assert len(page["items"]) == 2

    page2 = client.get("/api/v1/games?page=3&page_size=2").json()
    assert len(page2["items"]) == 1


def test_get_game_returns_positions_and_mistakes(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    make_position(db, game, ply=0)
    make_position(db, game, ply=1, san="e4")
    make_mistake(db, game, ply=5)

    response = client.get(f"/api/v1/games/{game.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == game.id
    assert data["pgn"].startswith("[Event")
    assert len(data["positions"]) == 2
    assert data["positions"][0]["ply"] == 0
    assert data["positions"][1]["san"] == "e4"
    assert len(data["mistakes"]) == 1
    assert data["mistakes"][0]["ply"] == 5


def test_get_game_404_when_missing(client) -> None:
    response = client.get("/api/v1/games/99999")
    assert response.status_code == 404


# ---- POST /games/{id}/refresh ----------------------------------------------

class _StubRefreshSource:
    """Stands in for the registry-built source in refresh route tests."""

    name = "lichess_online"

    def __init__(self, record=None, error=None):
        self._record = record
        self._error = error

    async def fetch_game_by_id(self, user, game_id):
        if self._error is not None:
            raise self._error
        return self._record


def _override_settings(username: str = "configured_user"):
    from backend.app.config import Settings

    return lambda: Settings(lichess_username=username, _env_file=None)


def test_refresh_updates_game_and_reports_eval_arrival(client, db, monkeypatch) -> None:
    from dataclasses import replace as dc_replace

    from backend.app.config import get_settings
    from backend.app.main import app
    from backend.app.sources.lichess_online import parse_pgn_game

    user = make_user(db)
    game = make_game(db, user, has_evals=False, analyzed=True)

    refreshed_pgn = (
        '[Event "Test"]\n[Site "https://lichess.org/g0000001"]\n'
        f'[White "{game.white}"]\n[Black "{game.black}"]\n[Result "1-0"]\n\n'
        "1. e4 { [%eval 0.2] } e5 { [%eval 0.1] } 1-0\n"
    )
    record = parse_pgn_game(refreshed_pgn, user.lichess_username)
    assert record is not None and record.has_evals
    record = dc_replace(record, source_game_id=game.source_game_id)

    monkeypatch.setattr(
        "backend.app.api.games.get_source",
        lambda name, settings: _StubRefreshSource(record=record),
    )
    app.dependency_overrides[get_settings] = _override_settings(user.lichess_username)
    try:
        response = client.post(f"/api/v1/games/{game.id}/refresh")
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {
        "game_id": game.id,
        "pgn_changed": True,
        "had_evals_before": False,
        "has_evals": True,
    }
    detail = client.get(f"/api/v1/games/{game.id}").json()
    assert detail["has_evals"] is True
    assert detail["analyzed_at"] is None  # stale analysis marked pending


def test_refresh_conflict_when_user_no_longer_a_player(client, db, monkeypatch) -> None:
    from backend.app.config import get_settings
    from backend.app.main import app

    user = make_user(db)
    game = make_game(db, user)
    monkeypatch.setattr(
        "backend.app.api.games.get_source",
        lambda name, settings: _StubRefreshSource(record=None),
    )
    app.dependency_overrides[get_settings] = _override_settings(user.lichess_username)
    try:
        response = client.post(f"/api/v1/games/{game.id}/refresh")
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 409


def test_refresh_maps_upstream_404(client, db, monkeypatch) -> None:
    import httpx

    from backend.app.config import get_settings
    from backend.app.main import app

    user = make_user(db)
    game = make_game(db, user)
    request = httpx.Request("GET", "https://lichess.org/game/export/g0000001")
    error = httpx.HTTPStatusError(
        "404", request=request, response=httpx.Response(404, request=request)
    )
    monkeypatch.setattr(
        "backend.app.api.games.get_source",
        lambda name, settings: _StubRefreshSource(error=error),
    )
    app.dependency_overrides[get_settings] = _override_settings(user.lichess_username)
    try:
        response = client.post(f"/api/v1/games/{game.id}/refresh")
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert response.status_code == 404
    assert "not found on lichess_online" in response.json()["detail"]


def test_refresh_404_when_game_missing(client) -> None:
    assert client.post("/api/v1/games/99999/refresh").status_code == 404
