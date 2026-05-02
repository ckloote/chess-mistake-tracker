from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.app.sources.lichess_online import (
    _extract_lichess_game_id,
    parse_pgn_game,
    parse_pgn_stream,
)

FIXTURE = Path(__file__).parent / "fixtures" / "lichess_two_games.pgn"


@pytest.fixture()
def two_games_pgn() -> str:
    return FIXTURE.read_text()


def test_extract_lichess_game_id_strips_color_suffix() -> None:
    assert _extract_lichess_game_id("https://lichess.org/abc12345") == "abc12345"
    assert _extract_lichess_game_id("https://lichess.org/abc12345/black") == "abc12345"
    assert _extract_lichess_game_id("") == ""


def test_parse_pgn_stream_picks_up_both_games(two_games_pgn: str) -> None:
    records = parse_pgn_stream(two_games_pgn, "configured_user")
    assert len(records) == 2

    first, second = records

    assert first.source_game_id == "abcd1234"
    assert first.user_color == "black"
    assert first.white == "alice"
    assert first.black == "configured_user"
    assert first.result == "1-0"
    assert first.white_elo == 1850
    assert first.black_elo == 1900
    assert first.time_control == "300+0"
    assert first.has_evals is True
    assert first.played_at == datetime(2025, 1, 15, 12, 34, 56, tzinfo=timezone.utc)

    assert second.source_game_id == "wxyz5678"
    assert second.user_color == "white"
    assert second.has_evals is False
    assert second.played_at == datetime(2025, 2, 20, 9, 0, 0, tzinfo=timezone.utc)


def test_parse_pgn_stream_skips_games_user_didnt_play(two_games_pgn: str) -> None:
    records = parse_pgn_stream(two_games_pgn, "someone_else")
    assert records == []


def test_parse_pgn_game_returns_none_when_user_isnt_player(two_games_pgn: str) -> None:
    # Take just the first game's text up to the next [Event header
    first_game = two_games_pgn.split("[Event \"Rated bullet game\"]")[0]
    assert parse_pgn_game(first_game, "alice").user_color == "white"
    assert parse_pgn_game(first_game, "no_one") is None


def test_username_match_is_case_insensitive(two_games_pgn: str) -> None:
    records = parse_pgn_stream(two_games_pgn, "Configured_User")
    assert len(records) == 2
