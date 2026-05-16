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
