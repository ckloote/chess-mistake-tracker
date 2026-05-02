from pathlib import Path

import pytest

from backend.app.sources.lichess_study import (
    _extract_chapter_id,
    _resolve_user_color,
    _validate_study_id,
    parse_study_pgn,
)

FIXTURE = Path(__file__).parent / "fixtures" / "lichess_study.pgn"


@pytest.fixture()
def study_pgn() -> str:
    return FIXTURE.read_text()


def test_extract_chapter_id_happy_path() -> None:
    url = "https://lichess.org/study/STUDYone/chap0001"
    assert _extract_chapter_id(url, "STUDYone") == "chap0001"


def test_extract_chapter_id_returns_none_when_study_does_not_match() -> None:
    url = "https://lichess.org/study/OTHER123/chap0001"
    assert _extract_chapter_id(url, "STUDYone") is None


def test_extract_chapter_id_returns_none_on_unrelated_url() -> None:
    assert _extract_chapter_id("https://lichess.org/abc12345", "STUDYone") is None
    assert _extract_chapter_id("", "STUDYone") is None


def test_validate_study_id_rejects_garbage() -> None:
    _validate_study_id("STUDYone")
    _validate_study_id("aBcD1234")
    with pytest.raises(ValueError):
        _validate_study_id("too-short")
    with pytest.raises(ValueError):
        _validate_study_id("contains/slash")
    with pytest.raises(ValueError):
        _validate_study_id("")


def test_parse_study_picks_up_chapters_user_played(study_pgn: str) -> None:
    records = parse_study_pgn(study_pgn, "STUDYone", "configured_user")
    assert len(records) == 2

    by_id = {r.source_game_id: r for r in records}
    assert "STUDYone:chap0001" in by_id
    assert "STUDYone:chap0002" in by_id
    assert "STUDYone:chap0003" not in by_id

    assert by_id["STUDYone:chap0001"].user_color == "white"
    assert by_id["STUDYone:chap0002"].user_color == "black"
    for r in records:
        assert r.source == "lichess_study"


def test_parse_study_returns_empty_when_user_in_no_chapters(study_pgn: str) -> None:
    assert parse_study_pgn(study_pgn, "STUDYone", "no_one") == []


def test_parse_study_skips_chapters_pointing_at_other_studies(study_pgn: str) -> None:
    # Same fixture, different study ID — every chapter's Site URL references STUDYone,
    # so against OTHERONE we should get nothing.
    assert parse_study_pgn(study_pgn, "OTHERONE", "configured_user") == []


def test_resolve_user_color_matches_username() -> None:
    assert _resolve_user_color("alice", "bob", "alice", []) == "white"
    assert _resolve_user_color("alice", "bob", "bob", []) == "black"
    assert _resolve_user_color("alice", "bob", "carol", []) is None


def test_resolve_user_color_matches_alias_case_insensitively() -> None:
    assert _resolve_user_color("CJK", "Clark Henry", "phaedrus317", ["cjk"]) == "white"
    assert _resolve_user_color("Opp", "Christopher Kloote", "phaedrus317", ["Christopher Kloote"]) == "black"


def test_resolve_user_color_skips_when_neither_username_nor_alias_matches() -> None:
    assert _resolve_user_color("Carlsen", "Caruana", "phaedrus317", ["CJK"]) is None


def test_parse_study_with_aliases_picks_up_otb_chapter() -> None:
    """Sanity-check the alias path against an OTB-shaped chapter where the user
    is recorded by initials, which is exactly the live-data case."""
    otb_pgn = (
        '[Event "Indy Chess Spring League"]\n'
        '[ChapterURL "https://lichess.org/study/STUDYone/abcdefgh"]\n'
        '[Result "1-0"]\n'
        '[White "CJK"]\n'
        '[Black "Clark Henry"]\n'
        '[UTCDate "2026.04.24"]\n'
        '\n'
        '1. Nf3 d5 1-0\n'
    )
    records = parse_study_pgn(otb_pgn, "STUDYone", "phaedrus317", aliases=["CJK"])
    assert len(records) == 1
    assert records[0].user_color == "white"
    assert records[0].source_game_id == "STUDYone:abcdefgh"
