def test_get_settings_returns_defaults_on_first_call(client) -> None:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    data = response.json()
    # Bootstrapped from config.Settings defaults (see .env.example).
    assert data["winrate_inaccuracy"] == 5.0
    assert data["winrate_mistake"] == 10.0
    assert data["winrate_blunder"] == 20.0
    assert data["suppress_below"] == 30.0
    assert data["suppress_above_before"] == 90.0
    assert data["suppress_above_after"] == 80.0
    assert isinstance(data["lichess_study_ids"], list)


def test_patch_settings_partial_update_persists(client) -> None:
    # Touch one threshold and one list field.
    response = client.patch(
        "/api/v1/settings",
        json={"winrate_blunder": 25.0, "lichess_study_ids": ["abcd1234"]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["winrate_blunder"] == 25.0
    assert data["lichess_study_ids"] == ["abcd1234"]
    # Untouched fields retain defaults.
    assert data["winrate_mistake"] == 10.0

    follow_up = client.get("/api/v1/settings").json()
    assert follow_up["winrate_blunder"] == 25.0
    assert follow_up["lichess_study_ids"] == ["abcd1234"]


def test_patch_settings_rejects_out_of_range_threshold(client) -> None:
    response = client.patch("/api/v1/settings", json={"winrate_blunder": 200.0})
    assert response.status_code == 422
