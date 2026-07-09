"""Registry wiring: sources are built from the AppSettings row, so
PATCH /settings edits (study ids, aliases) govern imports — not the env."""
from __future__ import annotations

import pytest

from backend.app.models import AppSettings
from backend.app.sources.chesscom import ChessComSource
from backend.app.sources.lichess_online import LichessOnlineSource
from backend.app.sources.lichess_study import LichessStudySource
from backend.app.sources.registry import get_source, known_sources


def _settings_row(**overrides) -> AppSettings:
    values = dict(
        id=1,
        winrate_inaccuracy=5.0,
        winrate_mistake=10.0,
        winrate_blunder=20.0,
        suppress_below=30.0,
        suppress_above_before=90.0,
        suppress_above_after=80.0,
        lichess_study_ids=[],
        study_player_aliases=[],
    )
    values.update(overrides)
    return AppSettings(**values)


def test_study_source_built_from_app_settings_row() -> None:
    row = _settings_row(
        lichess_study_ids=["abcd1234", "efgh5678"],
        study_player_aliases=["CJK", "C. Kloote"],
    )
    source = get_source("lichess_study", row)
    assert isinstance(source, LichessStudySource)
    assert source._study_ids == ["abcd1234", "efgh5678"]
    assert source._aliases == ["CJK", "C. Kloote"]


def test_study_source_with_empty_row_has_no_ids() -> None:
    """Regression for B4: an empty DB row must yield an empty source even if
    LICHESS_STUDY_IDS is set in the environment — the DB is the source of
    truth after first-run seeding."""
    source = get_source("lichess_study", _settings_row())
    assert source._study_ids == []
    assert source._aliases == []


def test_invalid_stored_study_id_raises_value_error() -> None:
    row = _settings_row(lichess_study_ids=["not a study id"])
    with pytest.raises(ValueError, match="Invalid Lichess study id"):
        get_source("lichess_study", row)


def test_online_source_ignores_settings() -> None:
    source = get_source("lichess_online", _settings_row())
    assert isinstance(source, LichessOnlineSource)


def test_chesscom_source_ignores_settings() -> None:
    source = get_source("chesscom", _settings_row())
    assert isinstance(source, ChessComSource)


def test_unknown_source_raises_key_error() -> None:
    with pytest.raises(KeyError):
        get_source("chess24", _settings_row())
    assert known_sources() == ["chesscom", "lichess_online", "lichess_study"]
