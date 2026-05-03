import math

import pytest

from backend.app.chess_utils.winrate import (
    cp_to_winrate,
    severity_for_drop,
    winrate_drop,
    winrate_for_color,
)


def test_cp_to_winrate_at_zero_is_50_percent() -> None:
    assert cp_to_winrate(0) == pytest.approx(50.0)


def test_cp_to_winrate_clamps_extremes() -> None:
    # cp values outside [-1000, 1000] should clamp, not blow up
    assert cp_to_winrate(5000) == pytest.approx(cp_to_winrate(1000))
    assert cp_to_winrate(-5000) == pytest.approx(cp_to_winrate(-1000))


def test_cp_to_winrate_is_symmetric_about_50() -> None:
    for cp in (50, 200, 800):
        white = cp_to_winrate(cp)
        black = cp_to_winrate(-cp)
        assert white + black == pytest.approx(100.0)


def test_cp_to_winrate_monotonic() -> None:
    last = -math.inf
    for cp in range(-1000, 1001, 50):
        v = cp_to_winrate(cp)
        assert v >= last
        last = v


def test_winrate_for_color_flips_for_black() -> None:
    # +200cp = white slightly winning. From white's view: ~67%. From black's: ~33%.
    white_view = winrate_for_color(200, None, "white")
    black_view = winrate_for_color(200, None, "black")
    assert white_view + black_view == pytest.approx(100.0)
    assert white_view > 50.0
    assert black_view < 50.0


def test_winrate_for_color_handles_mate_for_white() -> None:
    # white mates -> very high white winrate, very low black winrate
    white_view = winrate_for_color(None, 3, "white")
    black_view = winrate_for_color(None, 3, "black")
    assert white_view is not None and white_view > 95.0
    assert black_view is not None and black_view < 5.0


def test_winrate_for_color_handles_mate_for_black() -> None:
    white_view = winrate_for_color(None, -3, "white")
    black_view = winrate_for_color(None, -3, "black")
    assert white_view is not None and white_view < 5.0
    assert black_view is not None and black_view > 95.0


def test_winrate_for_color_returns_none_when_no_eval() -> None:
    assert winrate_for_color(None, None, "white") is None
    assert winrate_for_color(None, None, "black") is None


def test_winrate_drop_subtracts() -> None:
    assert winrate_drop(60.0, 30.0) == 30.0
    assert winrate_drop(40.0, 70.0) == -30.0
    assert winrate_drop(None, 50.0) is None
    assert winrate_drop(50.0, None) is None


def test_severity_thresholds() -> None:
    # Defaults from DESIGN.md: 5 / 10 / 20
    assert severity_for_drop(4.9, 5, 10, 20) is None
    assert severity_for_drop(5.0, 5, 10, 20) == "inaccuracy"
    assert severity_for_drop(9.99, 5, 10, 20) == "inaccuracy"
    assert severity_for_drop(10.0, 5, 10, 20) == "mistake"
    assert severity_for_drop(19.99, 5, 10, 20) == "mistake"
    assert severity_for_drop(20.0, 5, 10, 20) == "blunder"
    assert severity_for_drop(80.0, 5, 10, 20) == "blunder"
