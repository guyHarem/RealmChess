import copy
import functools
import threading
import time

from ai.levels import LEVELS, accepts_draw, think_time
from api.clock import ChessClock
from api.thinker import Busy, think
import random

from engine.board import CLASSIC_PORTALS, EXTRA_PAWN_SQUARES, shuffled_portals
from engine.game_state import GameState
from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn, Rock

PIECE_CLASSES = {
    "King": King,
    "Queen": Queen,
    "Rook": Rook,
    "Bishop": Bishop,
    "Knight": Knight,
    "Pawn": Pawn
}


def other(color):
    return "black" if color == "white" else "white"


def locked(method):
    """The web server answers several requests at once (two players, each asking every
    second). Only one of them may touch a game at a time."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


class GameManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.game = GameState()
        self.clock = None         # ChessClock, or None for an untimed game
        # An ending the rules engine doesn't know (resignation, agreed draw, timeout):
        # {"kind", "winner"}, plus "draw_reason" when a timeout ends in a draw
        self.result = None
        self._clock_stack = []    # clock snapshot before each turn, so undo can put the time back
        self._now = time.monotonic
        self.computer = None      # {"color", "level"} when the computer plays one side
        self._think = think       # how the computer thinks: think(game, level, seconds) -> dict (see api/thinker.py)
        self._version = 0         # goes up with every change, so a slow computer move can tell it is out of date
        self._thinking_about = None   # the version the computer is thinking about right now, if any
        # How the game was started (new_game's arguments), so it can be replayed on another
        # server (api/handoff.py); None once the position has been edited by hand
        self.options = {"rocks": True, "move_limit": 50, "clock": None, "computer": None}

    # ==================== HELPERS ====================

    def _get_status(self, draw_reason):
        player = self.game.current_player
        if self.result is not None:
            return self.result["kind"]  # "resigned", "agreed_draw" or "timeout"
        elif self.game.is_checkmate(player):
            return "checkmate"
        elif draw_reason == "stalemate":
            return "stalemate"
        elif draw_reason is not None:
            return "draw"  # a draw ends the game even if the player is in check
        elif self.game.is_in_check(player):
            return "check"
        else:
            return "ongoing"

    def _check_flag(self):
        """End the game if the player to move has run out of time"""
        if self.clock is not None and self.result is None:
            flagged = self.clock.flagged()
            if flagged is not None:
                self._version += 1
                opponent = other(flagged)
                # Running out of time only loses to an opponent who could still deliver checkmate
                if self.game.has_insufficient_material(opponent):
                    self.result = {"kind": "timeout", "winner": None,
                                   "draw_reason": "timeout_insufficient_material"}
                else:
                    self.result = {"kind": "timeout", "winner": opponent}
                self.clock.stop()

    def _is_over(self):
        """True once the game has ended: by a result, or by the rules (checkmate or any draw)"""
        self._check_flag()
        return self.result is not None or self._get_status(self.game.get_draw_reason()) not in ("ongoing", "check")

    def _require_ongoing(self):
        if self._is_over():
            raise ValueError("The game is over")

    def _state_response(self):
        self._check_flag()
        if self.result is not None:
            draw_reason = self.result.get("draw_reason")
        else:
            draw_reason = self.game.get_draw_reason()
        status = self._get_status(draw_reason)

        winner = None
        if self.result is not None:
            winner = self.result["winner"]
        elif status == "checkmate":
            winner = other(self.game.current_player)

        # Nobody's time runs once the game is decided
        if self.clock is not None and status not in ("ongoing", "check"):
            self.clock.stop()

        board = self.game.get_board_state()
        return {
            "success": True,
            "version": self._version,
            "current_player": self.game.current_player,
            # Copies, so that the reply stays as it is while other requests move on
            "board": dict(board.board),
            "board_size": {"size": board.size, "z_min": board.z_min, "z_max": board.z_max},
            "status": status,
            "winner": winner,
            "draw_reason": draw_reason,
            "halfmove_clock": self.game.halfmove_clock,
            "move_limit": self.game.move_limit,
            "clock": self.clock.to_json() if self.clock is not None else None,
            "computer": dict(self.computer) if self.computer is not None else None,
            "pending_promotion": self.game.pending_promotion,
            # Pairs of linked cells: a piece ending its move on an empty one comes out of the other
            "portals": [[list(a), list(b)] for a, b in board.portal_pairs()],
            "move_history": [dict(move) for move in self.game.move_history]
        }

    def _error_response(self, error):
        response = self._state_response()
        response["success"] = False
        response["error"] = str(error)
        return response

    # ==================== GAME SETUP ====================

    @locked
    def new_game(self, rocks=True, move_limit=50, clock=None, computer=None, portals=None):
        """clock: None for an untimed game, or {"initial": seconds, "increment": seconds}
        computer: None for two human players, or {"color": "black", "level": "easy" | "medium" | "hard"}
        portals: None, "classic", "shuffle" (a random mirrored layout), or the pairs themselves
        [[[x,y,z], [x,y,z]], ...] (how a game is replayed)"""
        try:
            if type(move_limit) is not int or not 1 <= move_limit <= 500:
                raise ValueError("move_limit must be a whole number from 1 to 500")

            if computer is not None:
                if (not isinstance(computer, dict) or computer.get("color") not in ("white", "black")
                        or computer.get("level") not in LEVELS):
                    raise ValueError('computer must be {"color": "white" or "black", "level": "easy", "medium" or "hard"}')
                computer = {"color": computer["color"], "level": computer["level"]}

            new_clock = None
            if clock is not None:
                initial = clock.get("initial") if isinstance(clock, dict) else None
                increment = clock.get("increment", 0) if isinstance(clock, dict) else None
                if type(initial) is not int or not 10 <= initial <= 6 * 3600:
                    raise ValueError("clock.initial must be a whole number of seconds from 10 to 21600")
                if type(increment) is not int or not 0 <= increment <= 300:
                    raise ValueError("clock.increment must be a whole number of seconds from 0 to 300")
                new_clock = ChessClock(initial, increment, now=lambda: self._now())

            game = GameState(move_limit=move_limit)
            if not rocks:
                board = game.get_board_state()
                for coord, piece in list(board.board.items()):
                    if isinstance(piece, Rock):
                        board.remove_piece(coord)
                game.reset_tracking()
            if portals is not None:
                game.board.set_portals(self._portal_layout(portals, game.board))
            self._replace_game(game, new_clock, computer)
            self.options = {"rocks": bool(rocks), "move_limit": move_limit,
                            "clock": {"initial": initial, "increment": increment} if new_clock is not None else None,
                            "computer": computer,
                            # the exact cells, so a shuffled layout replays the same
                            "portals": [[list(a), list(b)] for a, b in game.board.portal_pairs()] or None}
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @staticmethod
    def _portal_layout(portals, board):
        if portals == "classic":
            return CLASSIC_PORTALS
        if portals == "shuffle":
            return shuffled_portals(random.Random(), board)
        if (not isinstance(portals, list) or not 1 <= len(portals) <= 4 or
                not all(isinstance(pair, list) and len(pair) == 2 for pair in portals)):
            raise ValueError('portals must be "classic", "shuffle" or a list of up to 4 pairs of cells')
        pairs = []
        for pair in portals:
            cells = []
            for cell in pair:
                if not isinstance(cell, list) or len(cell) != 3 or not all(type(n) is int for n in cell):
                    raise ValueError("A portal cell is [x, y, z]")
                if board.get_piece(tuple(cell)) is not None:
                    raise ValueError("A portal cannot be where a piece stands")
                cells.append(tuple(cell))
            pairs.append(cells)
        return pairs

    def _replace_game(self, game, clock=None, computer=None):
        self.options = None   # new_game() fills it in; any other new position cannot be replayed
        self.game = game
        self.clock = clock
        self.result = None
        self._clock_stack = []
        self.computer = computer
        self._version += 1

    def _mark_check(self, response):
        """Note on the last history entry whether that move gave check or checkmate (for move notation)"""
        if self.game.move_history and self.game.pending_promotion is None:
            status = response["status"]
            check = status if status in ("check", "checkmate") else None
            self.game.move_history[-1]["check"] = response["move_history"][-1]["check"] = check
        return response

    # ==================== QUERIES (READ-ONLY) ====================

    @locked
    def get_state(self):
        return self._state_response()

    @locked
    def get_legal_moves(self, from_coord):
        try:
            piece = self.game.get_board_state().get_piece(from_coord)

            # Only the player to move has legal moves, none while a promotion is pending,
            # and none once the game is over
            if (piece is None or isinstance(piece, Rock) or
                    piece.color != self.game.current_player or
                    self.game.pending_promotion is not None or
                    self._is_over()):
                moves = []
            else:
                moves = self.game.get_legal_moves(from_coord)

            return {
                "success": True,
                "legal_moves": moves,
                "current_player": self.game.current_player
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "current_player": self.game.current_player
            }

    # ==================== MOVES (STATE-CHANGING) ====================

    def _finish_turn(self, mover):
        if self.clock is not None and self.game.current_player != mover:
            self.clock.finish_turn(mover, self.game.current_player)

    def _computer_to_move(self):
        return self.computer is not None and self.game.current_player == self.computer["color"]

    @locked
    def make_move(self, from_coord, to_coord, by_computer=False):
        try:
            self._require_ongoing()
            if self._computer_to_move() and not by_computer:
                raise ValueError("It is the computer's turn")

            mover = self.game.current_player
            snapshot = self.clock.snapshot() if self.clock is not None else None
            ambiguous_from = self.game.get_ambiguous_origins(from_coord, to_coord)
            self.game.make_move(from_coord, to_coord)
            # For move notation: the other pieces of the same kind that could have made this move
            self.game.move_history[-1]["ambiguous_from"] = ambiguous_from
            self._clock_stack.append(snapshot)
            self._version += 1
            self._finish_turn(mover)
            return self._mark_check(self._state_response())
        except ValueError as e:
            return self._error_response(e)

    @locked
    def promote_pawn(self, coord, new_piece, by_computer=False):
        try:
            self._require_ongoing()
            if self._computer_to_move() and not by_computer:
                raise ValueError("It is the computer's turn")

            mover = self.game.current_player
            self.game.promote_pawn(coord, new_piece)
            self._version += 1
            self._finish_turn(mover)
            return self._mark_check(self._state_response())
        except ValueError as e:
            return self._error_response(e)

    # ==================== THE COMPUTER PLAYER ====================

    def computer_move(self):
        """Let the computer think and play its move. The thinking takes seconds and the game
        may change meanwhile (undo, new game); a move for a position that is gone is dropped."""
        try:
            with self.lock:
                self._require_ongoing()
                if self.computer is None:
                    raise ValueError("This game has no computer player")
                if not self._computer_to_move() or self.game.pending_promotion is not None:
                    raise ValueError("It is not the computer's turn")
                version = self._version
                if self._thinking_about == version:
                    raise ValueError("The computer is already thinking")

                color, level = self.computer["color"], self.computer["level"]
                clock_left = self.clock.time_left(color) if self.clock is not None else None
                increment = self.clock.increment if self.clock is not None else 0
                self._thinking_about = version
                position = copy.deepcopy(self.game)   # its own copy: the game stays free meanwhile

            try:
                thought = self._think(position, level, think_time(level, clock_left, increment))
            finally:
                with self.lock:
                    if self._thinking_about == version:
                        self._thinking_about = None

            with self.lock:
                if self._version != version:
                    raise ValueError("The position changed while the computer was thinking")
                if thought is None:
                    raise ValueError("The computer has no legal move")

                response = self.make_move(thought["from"], thought["to"], by_computer=True)
                if response["success"] and self.game.pending_promotion is not None:
                    piece = PIECE_CLASSES[thought["promotion"] or "Queen"](color)
                    response = self.promote_pawn(thought["to"], piece, by_computer=True)
                response["thought"] = {key: thought[key] for key in ("score", "depth", "nodes", "seconds", "mate_in")}
                return response
        except ValueError as e:
            with self.lock:
                response = self._error_response(e)
                if isinstance(e, Busy):
                    response["busy"] = True   # not a fault: the page asks again shortly
                return response

    HINT_SECONDS = 1.0   # a hint thinks this long at the strongest level, whatever the game's level

    def hint(self):
        """The computer's suggestion for the player to move, without playing it. The answer is
        the game state plus "hint": {"from", "to", "promotion", "version"}; version is the
        position it is for, since the game may move on while it thinks."""
        try:
            with self.lock:
                self._require_ongoing()
                if self.game.pending_promotion is not None:
                    raise ValueError("Finish the promotion first")
                if self._computer_to_move():
                    raise ValueError("It is the computer's turn")
                version = self._version
                position = copy.deepcopy(self.game)
            thought = self._think(position, "hard", self.HINT_SECONDS)
            with self.lock:
                if thought is None:
                    raise ValueError("There is no legal move")
                response = self._state_response()
                response["hint"] = {"from": thought["from"], "to": thought["to"],
                                    "promotion": thought["promotion"], "version": version}
                return response
        except ValueError as e:
            with self.lock:
                response = self._error_response(e)
                if isinstance(e, Busy):
                    response["busy"] = True
                return response

    # ==================== ENDING THE GAME BY CHOICE ====================

    @locked
    def resign(self, color=None):
        try:
            if color is None:
                # Against the computer only the human can resign; otherwise the player to move does
                color = other(self.computer["color"]) if self.computer is not None else self.game.current_player
            if color not in ("white", "black"):
                raise ValueError(f"Invalid color: {color}")
            self._require_ongoing()
            self.result = {"kind": "resigned", "winner": other(color)}
            self._version += 1
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @locked
    def agree_draw(self):
        """Both players agree to a draw. Against the computer this is an offer it may decline."""
        try:
            self._require_ongoing()
            if self.computer is not None and not accepts_draw(self.game, self.computer["color"], self.computer["level"]):
                response = self._error_response("The computer declines the draw")
                response["draw_declined"] = True
                return response
            self.result = {"kind": "agreed_draw", "winner": None}
            self._version += 1
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    # ==================== RECOVERY ====================

    @locked
    def undo_move(self):
        """Take back the last turn. Also reopens a game that ended by resignation, agreement or timeout,
        and puts the clocks back to where they were before that turn. Against the computer its
        reply is taken back too, so it is the human's move again."""
        if not self._undo_one():
            return self._error_response("No moves to undo")
        if self._computer_to_move():
            self._undo_one()
        return self._state_response()

    def _undo_one(self):
        if not self.game.undo_move():
            return False
        self.result = None
        self._version += 1
        snapshot = self._clock_stack.pop() if self._clock_stack else None
        if self.clock is not None and snapshot is not None:
            self.clock.restore(snapshot)
        return True

    # ==================== SANDBOX (TESTING ONLY) ====================
    # Edit the position directly to test move/capture behavior. Every edit
    # starts a fresh position: move history and undo are cleared.

    def _create_piece(self, piece_type, color, coord, size=8):
        if piece_type == "Rock":
            return Rock()
        if piece_type not in PIECE_CLASSES:
            raise ValueError(f"Invalid piece type: {piece_type}")
        if color not in ("white", "black"):
            raise ValueError(f"Invalid color: {color}")

        piece = PIECE_CLASSES[piece_type](color)

        # Only pieces on their starting squares keep double-step / castling rights
        x, y, z = coord
        home_rank = 0 if color == "white" else size - 1
        pawn_rank = 1 if color == "white" else size - 2
        if isinstance(piece, Pawn):
            # On the full board the pawns in Space and the Abyss start on the b and g files; a
            # smaller board with all five layers (a lesson) lets any of them start there
            start_layer = z == 0 or ((x, z) in EXTRA_PAWN_SQUARES if size == 8 else abs(z) == 2)
            piece.has_moved = not (y == pawn_rank and start_layer)
        elif isinstance(piece, King):
            piece.has_moved = size != 8 or (x, y, z) != (4, home_rank, 0)
        elif isinstance(piece, Rook):
            piece.has_moved = size != 8 or (x, y, z) not in ((0, home_rank, 0), (7, home_rank, 0))
        return piece

    def _set_square(self, coord, piece):
        board = self.game.get_board_state()
        if board.get_piece(coord) is not None:
            board.remove_piece(coord)
        if piece is not None:
            board.set_piece(piece, coord)

    @locked
    def setup_position(self, pieces, current_player="white", rocks=True, size=8, z_min=-2, z_max=2, portals=None):
        """Replace the whole position. pieces: list of {"coord", "type", "color"} ("Rock" needs no color).
        size/z_min/z_max choose the board: 8, -2, 2 is the full board; lessons use 5, -1, 1.
        portals: pairs of cells [[[x,y,z], [x,y,z]], ...], or None."""
        try:
            if current_player not in ("white", "black"):
                raise ValueError(f"Invalid color: {current_player}")
            if type(size) is not int or not 4 <= size <= 8:
                raise ValueError("size must be a whole number from 4 to 8")
            if type(z_min) is not int or type(z_max) is not int or not -2 <= z_min <= 0 <= z_max <= 2:
                raise ValueError("layers must run from z_min (-2 to 0) to z_max (0 to 2)")

            game = GameState(size=size, z_min=z_min, z_max=z_max)
            game.board.board = {}
            # The standard rock layout only fits the full board
            if rocks and game.board.is_standard():
                game.board.init_rocks()
            for item in pieces:
                coord = item["coord"]
                game.board.is_valid_coordinate(coord)
                game.board.board[coord] = self._create_piece(item["type"], item.get("color"), coord, size)
            if portals:
                game.board.set_portals(self._portal_layout(portals, game.board))
            game.current_player = current_player
            game.reset_tracking()

            self._replace_game(game)
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @locked
    def place_piece(self, coord, piece_type, color):
        try:
            self._set_square(coord, self._create_piece(piece_type, color, coord, self.game.board.size))
            self.game.reset_tracking()
            self._replace_game(self.game)
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @locked
    def remove_piece(self, coord):
        try:
            self._set_square(coord, None)
            self.game.reset_tracking()
            self._replace_game(self.game)
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @locked
    def set_turn(self, player):
        try:
            if player not in ("white", "black"):
                raise ValueError(f"Invalid color: {player}")
            if self.game.pending_promotion is not None:
                raise ValueError("Promote the pawn before changing the turn!")
            self.game.current_player = player
            self.game.restart_draw_tracking()
            self.options = None
            self._version += 1
            return self._state_response()
        except ValueError as e:
            return self._error_response(e)

    @locked
    def set_rocks(self, enabled):
        board = self.game.get_board_state()
        for coord, piece in list(board.board.items()):
            if isinstance(piece, Rock):
                board.remove_piece(coord)
        if enabled and board.is_standard():
            board.init_rocks()  # overwrites any piece standing on a rock square
        self.game.reset_tracking()
        self._replace_game(self.game)
        return self._state_response()
