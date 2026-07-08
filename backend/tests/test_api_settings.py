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


def test_get_settings_reports_stockfish_availability(client, monkeypatch) -> None:
    """stockfish_available mirrors whether a binary resolves — the UI keys
    'analyzable locally' copy off it."""
    import backend.app.api.settings as settings_api

    monkeypatch.setattr(settings_api, "resolve_stockfish_path", lambda _: "/some/stockfish")
    assert client.get("/api/v1/settings").json()["stockfish_available"] is True

    monkeypatch.setattr(settings_api, "resolve_stockfish_path", lambda _: None)
    assert client.get("/api/v1/settings").json()["stockfish_available"] is False


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


def test_patch_settings_rejects_malformed_study_id(client) -> None:
    """Study ids are validated at write time (8 alphanumeric chars) so a typo
    fails here rather than at the next import."""
    response = client.patch(
        "/api/v1/settings", json={"lichess_study_ids": ["not-a-study-id"]}
    )
    assert response.status_code == 422
    assert "Invalid Lichess study id" in response.text


def test_import_study_source_uses_db_settings_not_env(client, db) -> None:
    """End-to-end B4 wiring: with the AppSettings row holding no study ids,
    POST /games/import for the study source returns 0 imported without any
    network attempt — regardless of what LICHESS_STUDY_IDS in the environment
    says (the env only seeds the row on first run)."""
    from backend.app.config import Settings, get_settings
    from backend.app.main import app
    from backend.tests.conftest import make_user

    make_user(db, "cfg_user")
    app.dependency_overrides[get_settings] = lambda: Settings(
        lichess_username="cfg_user",
        lichess_study_ids=["envstudy1"],  # must be ignored in favor of the DB
        _env_file=None,
    )
    try:
        # Force the row to exist and hold no study ids, whatever the env seeded.
        assert client.patch(
            "/api/v1/settings", json={"lichess_study_ids": []}
        ).status_code == 200

        response = client.post(
            "/api/v1/games/import", json={"source": "lichess_study"}
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["imported"] == 0
        assert data["skipped"] == 0
    finally:
        app.dependency_overrides.pop(get_settings, None)
