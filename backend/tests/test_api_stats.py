from datetime import datetime, timezone

from backend.tests.conftest import make_game, make_mistake, make_user


def _seed_classified(db) -> None:
    """A small mixed corpus: 4 mistakes, 3 classified, across two games and
    two months. Used by summary/breakdown/prescription tests below."""
    user = make_user(db)
    g_may = make_game(
        db, user, source_game_id="g0000001",
        played_at=datetime(2025, 5, 10, tzinfo=timezone.utc),
    )
    g_jun = make_game(
        db, user, source_game_id="g0000002",
        played_at=datetime(2025, 6, 10, tzinfo=timezone.utc),
    )
    make_mistake(
        db, g_may, ply=4, severity="blunder",
        suggested_step=4, classified_step=4, classified_awareness="didnt_see_it",
    )
    make_mistake(
        db, g_may, ply=6, severity="mistake",
        suggested_step=2, classified_step=4, classified_awareness="didnt_see_it",
        time_pressure=True,
    )
    make_mistake(
        db, g_jun, ply=4, severity="inaccuracy",
        suggested_step=3, classified_step=3, classified_awareness="got_it_wrong",
        endgame=True,
    )
    # Unclassified — counts in totals but not in classified buckets.
    make_mistake(db, g_jun, ply=10, severity="blunder", suggested_step=4)


def test_summary_returns_overall_counts(client, db) -> None:
    _seed_classified(db)
    response = client.get("/api/v1/stats/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_games"] == 2
    assert data["total_mistakes"] == 4
    assert data["classified"] == 3
    assert data["unclassified"] == 1


def test_summary_buckets_by_severity(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/summary").json()
    severity_map = {row["severity"]: row["count"] for row in data["by_severity"]}
    assert severity_map == {"blunder": 2, "inaccuracy": 1, "mistake": 1}


def test_summary_buckets_classified_step(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/summary").json()
    step_map = {row["step"]: row["count"] for row in data["by_classified_step"]}
    assert step_map == {3: 1, 4: 2}


def test_breakdown_step_x_awareness(client, db) -> None:
    _seed_classified(db)
    response = client.get("/api/v1/stats/breakdown?by=step_x_awareness")
    assert response.status_code == 200
    data = response.json()
    item_map = {row["label"]: row["count"] for row in data["items"]}
    assert item_map == {"step_3|got_it_wrong": 1, "step_4|didnt_see_it": 2}


def test_breakdown_time_pressure(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/breakdown?by=time_pressure").json()
    item_map = {row["label"]: row["count"] for row in data["items"]}
    assert item_map == {"normal": 3, "time_pressure": 1}


def test_breakdown_phase(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/breakdown?by=phase").json()
    item_map = {row["label"]: row["count"] for row in data["items"]}
    assert item_map == {"endgame": 1, "middlegame_or_opening": 3}


def test_breakdown_by_month(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/breakdown?by=month").json()
    item_map = {row["label"]: row["count"] for row in data["items"]}
    assert item_map == {"2025-05": 2, "2025-06": 2}


def test_breakdown_rejects_unknown_dimension(client) -> None:
    response = client.get("/api/v1/stats/breakdown?by=nonsense")
    assert response.status_code == 400


def test_training_prescription_ranks_top_cells(client, db) -> None:
    _seed_classified(db)
    data = client.get("/api/v1/stats/training-prescription").json()
    assert data["classified_mistakes"] == 3
    items = data["items"]
    # Top cell should be step 4 / didnt_see_it (count 2, share 2/3).
    assert items[0]["step"] == 4
    assert items[0]["awareness"] == "didnt_see_it"
    assert items[0]["count"] == 2
    assert abs(items[0]["share"] - (2 / 3)) < 1e-6
    assert "blunder check" in items[0]["suggestion"].lower()


def test_training_prescription_returns_empty_when_nothing_classified(client) -> None:
    data = client.get("/api/v1/stats/training-prescription").json()
    assert data == {"classified_mistakes": 0, "items": []}


# ---- Shared filters (F4) ----------------------------------------------------

def _seed_filterable(db) -> None:
    """Three games spanning both sources, both colors, blitz/rapid/OTB, and
    two months — each with distinguishable mistakes."""
    user = make_user(db)
    g_blitz_white = make_game(
        db, user, source="lichess_online", source_game_id="online01",
        user_color="white", time_control="300+3",
        played_at=datetime(2025, 5, 10, tzinfo=timezone.utc),
    )
    g_rapid_black = make_game(
        db, user, source="lichess_online", source_game_id="online02",
        user_color="black", time_control="900+10",
        played_at=datetime(2025, 6, 10, tzinfo=timezone.utc),
    )
    g_otb = make_game(
        db, user, source="lichess_study", source_game_id="study01:ch1",
        user_color="white", time_control=None,
        played_at=datetime(2025, 6, 20, tzinfo=timezone.utc),
    )
    make_mistake(
        db, g_blitz_white, ply=4, severity="blunder",
        classified_step=4, classified_awareness="didnt_see_it",
    )
    make_mistake(
        db, g_blitz_white, ply=8, severity="inaccuracy",
        classified_step=3, classified_awareness="got_it_wrong",
    )
    make_mistake(
        db, g_rapid_black, ply=5, severity="mistake",
        classified_step=2, classified_awareness="didnt_see_it",
    )
    make_mistake(
        db, g_otb, ply=9, severity="blunder",
        classified_step=1, classified_awareness="didnt_see_it",
    )


def test_summary_filters_by_source(client, db) -> None:
    _seed_filterable(db)
    data = client.get("/api/v1/stats/summary?source=lichess_study").json()
    assert data["total_games"] == 1
    assert data["total_mistakes"] == 1
    step_map = {row["step"]: row["count"] for row in data["by_classified_step"]}
    assert step_map == {1: 1}


def test_summary_filters_by_color(client, db) -> None:
    _seed_filterable(db)
    data = client.get("/api/v1/stats/summary?color=black").json()
    assert data["total_games"] == 1
    assert data["total_mistakes"] == 1
    severity_map = {row["severity"]: row["count"] for row in data["by_severity"]}
    assert severity_map == {"mistake": 1}


def test_summary_filters_by_date_range(client, db) -> None:
    _seed_filterable(db)
    data = client.get("/api/v1/stats/summary?from=2025-06-01&to=2025-06-15").json()
    assert data["total_games"] == 1  # only the rapid game
    assert data["total_mistakes"] == 1


def test_summary_filters_by_speed(client, db) -> None:
    _seed_filterable(db)
    blitz = client.get("/api/v1/stats/summary?speed=blitz").json()
    assert blitz["total_games"] == 1
    assert blitz["total_mistakes"] == 2
    unknown = client.get("/api/v1/stats/summary?speed=unknown").json()
    assert unknown["total_games"] == 1  # the OTB study game (no TimeControl)
    assert unknown["total_mistakes"] == 1


def test_summary_severity_filters_mistakes_not_games(client, db) -> None:
    _seed_filterable(db)
    data = client.get("/api/v1/stats/summary?severity=blunder").json()
    # Game count stays a property of the game slice; severity narrows mistakes.
    assert data["total_games"] == 3
    assert data["total_mistakes"] == 2
    step_map = {row["step"]: row["count"] for row in data["by_classified_step"]}
    assert step_map == {1: 1, 4: 1}


def test_summary_combines_filters(client, db) -> None:
    _seed_filterable(db)
    data = client.get(
        "/api/v1/stats/summary?source=lichess_online&severity=blunder"
    ).json()
    assert data["total_games"] == 2
    assert data["total_mistakes"] == 1


def test_breakdown_honors_filters(client, db) -> None:
    _seed_filterable(db)
    data = client.get(
        "/api/v1/stats/breakdown?by=month&source=lichess_online"
    ).json()
    item_map = {row["label"]: row["count"] for row in data["items"]}
    assert item_map == {"2025-05": 2, "2025-06": 1}


def test_prescription_honors_filters(client, db) -> None:
    _seed_filterable(db)
    data = client.get(
        "/api/v1/stats/training-prescription?color=white"
    ).json()
    assert data["classified_mistakes"] == 3
    cells = {(i["step"], i["awareness"]) for i in data["items"]}
    assert (2, "didnt_see_it") not in cells  # the black-game mistake


def test_stats_reject_invalid_filter_values(client) -> None:
    assert client.get("/api/v1/stats/summary?speed=hyperbullet").status_code == 422
    assert client.get("/api/v1/stats/summary?color=green").status_code == 422
    assert client.get("/api/v1/stats/summary?severity=catastrophe").status_code == 422
