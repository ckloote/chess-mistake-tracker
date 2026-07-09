from backend.app.chess_utils.time_control import parse_time_control, speed_of


def test_parse_time_control_standard_formats() -> None:
    assert parse_time_control("300+0") == (300, 0)
    assert parse_time_control("60+30") == (60, 30)
    assert parse_time_control("5400+30") == (5400, 30)


def test_parse_time_control_accepts_bare_seconds() -> None:
    # Some sources record just the base time, no increment.
    assert parse_time_control("600") == (600, 0)
    assert parse_time_control(" 300 ") == (300, 0)


def test_parse_time_control_returns_none_for_unparseable() -> None:
    assert parse_time_control(None) == (None, None)
    assert parse_time_control("") == (None, None)
    assert parse_time_control("OTB") == (None, None)
    assert parse_time_control("1/86400+0") == (None, None)


def test_speed_of_buckets() -> None:
    # estimated duration = initial + 40 * increment (Lichess convention)
    assert speed_of("60+0") == "bullet"
    assert speed_of("120+1") == "bullet"      # 160
    assert speed_of("180+0") == "blitz"       # boundary: 180 is blitz
    assert speed_of("300+3") == "blitz"       # 420
    assert speed_of("480+0") == "rapid"       # boundary: 480 is rapid
    assert speed_of("900+10") == "rapid"      # 1300
    assert speed_of("1500+0") == "classical"  # boundary: 1500 is classical
    assert speed_of("5400+30") == "classical"


def test_speed_of_unknown_for_unparseable() -> None:
    assert speed_of(None) == "unknown"
    assert speed_of("") == "unknown"
    assert speed_of("-") == "unknown"


def test_speed_of_correspondence_for_daily_form() -> None:
    # chess.com daily games: moves-per-period / seconds-per-period.
    assert speed_of("1/259200") == "correspondence"
    assert speed_of("1/86400") == "correspondence"
    # The per-move clock math stays undefined for these.
    assert parse_time_control("1/259200") == (None, None)
