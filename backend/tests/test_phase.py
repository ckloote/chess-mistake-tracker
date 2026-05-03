import chess

from backend.app.chess_utils.phase import (
    detected_transition,
    is_endgame,
    is_quiet_position,
    queens_off,
)


def test_starting_position_is_not_endgame() -> None:
    assert is_endgame(chess.Board()) is False
    assert queens_off(chess.Board()) is False


def test_kings_only_endgame() -> None:
    board = chess.Board("4k3/8/8/8/8/8/8/4K3 w - - 0 1")
    assert is_endgame(board) is True
    assert queens_off(board) is True


def test_rook_endgame_classified_as_endgame() -> None:
    # KRP vs KRP — clearly endgame
    board = chess.Board("4k3/8/8/8/8/8/4P3/4K2R w K - 0 1")
    assert is_endgame(board) is True


def test_queens_off_middlegame_can_still_be_middlegame() -> None:
    # Queens removed but both rooks and minors intact — not yet "endgame"
    # by material count alone.
    board = chess.Board("r1b1k2r/ppp1pppp/2n2n2/3p4/3P4/2N2N2/PPP1PPPP/R1B1K2R w KQkq - 0 1")
    assert queens_off(board) is True
    assert is_endgame(board) is False  # too much material still on the board


def test_detected_transition_fires_when_queens_come_off() -> None:
    before = chess.Board()
    # Push queens off via a contrived sequence — easier to do by FEN swap.
    after_no_q = chess.Board("rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1")
    assert detected_transition(before, after_no_q) is True


def test_detected_transition_fires_on_rook_capture() -> None:
    before = chess.Board()
    after_one_rook_gone = chess.Board("rnbqkbn1/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")
    assert detected_transition(before, after_one_rook_gone) is True


def test_detected_transition_quiet_minor_move() -> None:
    before = chess.Board()
    board = chess.Board()
    board.push_san("Nf3")
    assert detected_transition(before, board) is False


def test_is_quiet_position_in_starting_position() -> None:
    # Plenty of legal non-capturing, non-checking moves available — quiet.
    assert is_quiet_position(chess.Board()) is True


def test_is_quiet_position_false_when_in_check() -> None:
    board = chess.Board("rnb1kbnr/pppp1ppp/4p3/8/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")
    assert board.is_check()
    assert is_quiet_position(board) is False
