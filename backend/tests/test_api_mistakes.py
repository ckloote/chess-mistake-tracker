from datetime import datetime, timezone

from backend.tests.conftest import make_game, make_mistake, make_position, make_user


def test_list_mistakes_filters_by_game(client, db) -> None:
    user = make_user(db)
    g1 = make_game(db, user, source_game_id="g0000001")
    g2 = make_game(db, user, source_game_id="g0000002")
    make_mistake(db, g1, ply=5)
    make_mistake(db, g2, ply=7)

    only_g1 = client.get(f"/api/v1/mistakes?game_id={g1.id}").json()
    assert only_g1["total"] == 1
    assert only_g1["items"][0]["game_id"] == g1.id


def test_list_mistakes_filters_by_severity(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    make_mistake(db, game, ply=4, severity="blunder")
    make_mistake(db, game, ply=6, severity="inaccuracy")
    make_mistake(db, game, ply=8, severity="mistake")

    blunders = client.get("/api/v1/mistakes?severity=blunder").json()
    assert blunders["total"] == 1
    assert blunders["items"][0]["severity"] == "blunder"


def test_list_mistakes_filters_by_classification(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    make_mistake(db, game, ply=4, classified_step=4, classified_awareness="didnt_see_it")
    make_mistake(db, game, ply=6, classified_step=2, classified_awareness="got_it_wrong")
    make_mistake(db, game, ply=8)  # unclassified

    step4 = client.get("/api/v1/mistakes?step=4").json()
    assert step4["total"] == 1
    assert step4["items"][0]["classified_step"] == 4

    didnt_see = client.get("/api/v1/mistakes?awareness=didnt_see_it").json()
    assert didnt_see["total"] == 1

    unclassified = client.get("/api/v1/mistakes?unclassified_only=true").json()
    assert unclassified["total"] == 1
    assert unclassified["items"][0]["ply"] == 8


def test_list_mistakes_filters_by_time_pressure(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    make_mistake(db, game, ply=4, time_pressure=True)
    make_mistake(db, game, ply=6, time_pressure=False)

    pressured = client.get("/api/v1/mistakes?time_pressure=true").json()
    assert pressured["total"] == 1
    assert pressured["items"][0]["time_pressure_flag"] is True


def test_list_mistakes_filters_by_date_via_game_played_at(client, db) -> None:
    user = make_user(db)
    g_may = make_game(
        db, user, source_game_id="g0000010",
        played_at=datetime(2025, 5, 10, tzinfo=timezone.utc),
    )
    g_jun = make_game(
        db, user, source_game_id="g0000011",
        played_at=datetime(2025, 6, 10, tzinfo=timezone.utc),
    )
    make_mistake(db, g_may)
    make_mistake(db, g_jun)

    may_only = client.get("/api/v1/mistakes?from=2025-05-01&to=2025-05-31").json()
    assert may_only["total"] == 1
    assert may_only["items"][0]["game_id"] == g_may.id


def test_get_mistake_includes_surrounding_positions(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    make_position(db, game, ply=4, san="d4")
    make_position(db, game, ply=5, san="Nf6")
    make_position(db, game, ply=6, san="Bg5")
    mistake = make_mistake(db, game, ply=5)

    response = client.get(f"/api/v1/mistakes/{mistake.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == mistake.id
    assert data["game"]["id"] == game.id
    assert data["position_before"]["ply"] == 4
    assert data["position_at_move"]["ply"] == 5
    assert data["position_after_response"]["ply"] == 6


def test_get_mistake_404_when_missing(client) -> None:
    response = client.get("/api/v1/mistakes/99999")
    assert response.status_code == 404


def test_patch_mistake_records_classification_and_timestamps(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    mistake = make_mistake(db, game)
    assert mistake.classified_at is None

    response = client.patch(
        f"/api/v1/mistakes/{mistake.id}",
        json={
            "classified_step": 4,
            "classified_awareness": "didnt_see_it",
            "user_notes": "rushed the blunder check",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["classified_step"] == 4
    assert data["classified_awareness"] == "didnt_see_it"
    assert data["user_notes"] == "rushed the blunder check"
    assert data["classified_at"] is not None


def test_patch_mistake_partial_update_keeps_unset_fields(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    mistake = make_mistake(
        db, game, classified_step=3, classified_awareness="got_it_wrong"
    )

    response = client.patch(
        f"/api/v1/mistakes/{mistake.id}", json={"user_notes": "added a note"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["classified_step"] == 3  # unchanged
    assert data["classified_awareness"] == "got_it_wrong"  # unchanged
    assert data["user_notes"] == "added a note"


def test_patch_mistake_rejects_invalid_step(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    mistake = make_mistake(db, game)
    response = client.patch(
        f"/api/v1/mistakes/{mistake.id}", json={"classified_step": 9}
    )
    assert response.status_code == 422


def test_patch_mistake_can_toggle_flags(client, db) -> None:
    user = make_user(db)
    game = make_game(db, user)
    mistake = make_mistake(db, game, time_pressure=False)

    response = client.patch(
        f"/api/v1/mistakes/{mistake.id}",
        json={"time_pressure_flag": True, "transition_flag": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["time_pressure_flag"] is True
    assert data["transition_flag"] is True


def test_patch_mistake_404_when_missing(client) -> None:
    response = client.patch("/api/v1/mistakes/99999", json={"user_notes": "x"})
    assert response.status_code == 404


def test_patch_clearing_both_classification_fields_unclassifies(client, db) -> None:
    """Clearing step AND awareness must reset classified_at so the mistake
    returns to the unclassified queue (was: timestamp lingered)."""
    from backend.tests.conftest import make_game, make_mistake, make_user

    user = make_user(db)
    game = make_game(db, user)
    m = make_mistake(
        db, game, ply=5, classified_step=4, classified_awareness="didnt_see_it"
    )
    assert m.classified_at is not None

    response = client.patch(
        f"/api/v1/mistakes/{m.id}",
        json={"classified_step": None, "classified_awareness": None},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["classified_step"] is None
    assert data["classified_awareness"] is None
    assert data["classified_at"] is None

    queue = client.get("/api/v1/mistakes?unclassified_only=true").json()
    assert any(item["id"] == m.id for item in queue["items"])
