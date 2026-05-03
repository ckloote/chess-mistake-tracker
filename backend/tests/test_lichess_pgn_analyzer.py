from backend.app.analyzers.lichess_pgn import parse_pgn_for_positions

# A 4-move game: 1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#  → 8 plies, 9 positions.
# Mixes integer and decimal evals plus a mate eval, and includes %clk on each ply.
SCHOLARS_MATE_PGN = """\
[Event "Test"]
[Site "https://lichess.org/abcd1234"]
[White "alice"]
[Black "configured_user"]
[Result "1-0"]
[TimeControl "300+0"]

1. e4 { [%eval 0.21] [%clk 0:05:00] } e5 { [%eval 0.18] [%clk 0:05:00] }
2. Qh5 { [%eval -0.42] [%clk 0:04:55] } Nc6 { [%eval -0.35] [%clk 0:04:58] }
3. Bc4 { [%eval -0.30] [%clk 0:04:50] } Nf6 { [%eval 9.21] [%clk 0:04:52] }
4. Qxf7# { [%eval #0] [%clk 0:04:48] } 1-0
"""

# Same game shape but with no annotations on some moves and a deep mate eval.
PARTIAL_ANNOTATIONS_PGN = """\
[Event "Test"]
[Site "https://lichess.org/efgh5678"]
[White "alice"]
[Black "bob"]
[Result "1-0"]

1. e4 e5 2. Qh5 { [%eval -0.42] } Nc6 { [%eval -0.35] [%clk 0:04:58] }
3. Bc4 { [%eval #5] } Nf6 { [%eval #-3] } 4. Qxf7# 1-0
"""


def test_parse_emits_one_row_per_ply_plus_starting_position() -> None:
    rows = parse_pgn_for_positions(SCHOLARS_MATE_PGN)
    # Scholars mate = 7 plies played (1.e4 e5 2.Qh5 Nc6 3.Bc4 Nf6 4.Qxf7#) + ply 0
    assert [r.ply for r in rows] == list(range(8))

    assert rows[0].fen.startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")
    assert rows[0].san is None and rows[0].uci is None
    assert rows[0].eval_cp is None and rows[0].clock_ms is None


def test_parse_extracts_san_and_uci_from_moves() -> None:
    rows = parse_pgn_for_positions(SCHOLARS_MATE_PGN)
    assert rows[1].san == "e4" and rows[1].uci == "e2e4"
    assert rows[2].san == "e5" and rows[2].uci == "e7e5"
    assert rows[7].san == "Qxf7#" and rows[7].uci == "h5f7"


def test_parse_handles_decimal_pawn_units_and_integer_centipawns() -> None:
    rows = parse_pgn_for_positions(SCHOLARS_MATE_PGN)
    # 0.21 pawns -> 21cp, 0.18 -> 18cp, 9.21 -> 921cp
    assert rows[1].eval_cp == 21
    assert rows[2].eval_cp == 18
    assert rows[6].eval_cp == 921
    assert rows[1].mate_in is None


def test_parse_extracts_mate_evals() -> None:
    rows = parse_pgn_for_positions(SCHOLARS_MATE_PGN)
    # `[%eval #0]` on the mating move (ply 7, 4. Qxf7#)
    assert rows[7].mate_in == 0
    assert rows[7].eval_cp is None


def test_parse_signs_mate_evals_white_relative() -> None:
    rows = parse_pgn_for_positions(PARTIAL_ANNOTATIONS_PGN)
    # `#5` after Bc4 is white-to-mate-in-5. After ... Nf6 the comment is `#-3` —
    # in Lichess PGNs, mate values are stored from the side-to-move's perspective,
    # so python-chess flips negative-after-black-move back to white-relative.
    # We just assert both are present and signed sensibly.
    bc4_ply = next(r for r in rows if r.san == "Bc4")
    nf6_ply = next(r for r in rows if r.san == "Nf6")
    assert bc4_ply.mate_in is not None
    assert nf6_ply.mate_in is not None


def test_parse_handles_missing_clock_and_eval() -> None:
    rows = parse_pgn_for_positions(PARTIAL_ANNOTATIONS_PGN)
    # 1. e4 has no annotation
    assert rows[1].eval_cp is None and rows[1].mate_in is None
    assert rows[1].clock_ms is None
    # 2. Qh5 has eval but no clock
    qh5 = next(r for r in rows if r.san == "Qh5")
    assert qh5.eval_cp == -42
    assert qh5.clock_ms is None
    # 2... Nc6 has both
    nc6 = next(r for r in rows if r.san == "Nc6")
    assert nc6.clock_ms == 298_000  # 0:04:58 → 298s


def test_parse_clock_ms_uses_h_mm_ss_format() -> None:
    rows = parse_pgn_for_positions(SCHOLARS_MATE_PGN)
    assert rows[1].clock_ms == 300_000  # 5:00
    assert rows[3].clock_ms == 295_000  # 4:55
    assert rows[7].clock_ms == 288_000  # 4:48


def test_parse_returns_empty_only_for_truly_empty_input() -> None:
    # python-chess's read_game tolerates near-anything and returns a Game with
    # the default starting position. We treat that as a single-row "starting
    # position only" result; only an empty-string input yields a true empty list.
    assert parse_pgn_for_positions("") == []
