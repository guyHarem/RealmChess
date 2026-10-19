"""
The computer player thinks on its own fast board (ai/board.py). These tests hold it to the
real engine: the same legal moves, the same checks, the same position fingerprints, in
random games and random positions on every board size.

Seeds are fixed, so a failure is reproducible: the message names the seed.
"""
import random
import unittest

from ai.board import FastBoard, move_promotion
from api.game_manager import GameManager
from engine.game_state import GameState
from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn

PIECES = {"Queen": Queen, "Rook": Rook, "Bishop": Bishop, "Knight": Knight}


def state_of(board):
    """Everything a FastBoard remembers (apart from its undo list)"""
    return (list(board.cells), board.side, sorted(board.squares[0]), sorted(board.squares[1]),
            list(board.kings), list(board.counts), board.ep, board.ep_pawn, board.half,
            board.score, board.pieces_key, board.rights_key, board.key, list(board.history))


def engine_moves(game):
    return sorted((coord, move)
                  for coord, _ in game.get_all_pieces_of_color(game.current_player)
                  for move in set(game.get_legal_moves(coord)))


class FastBoardTestCase(unittest.TestCase):
    def assert_same_position(self, game, tag, board=None):
        """A FastBoard must agree with the engine about the position. `board` is one that was
        carried along move by move; without it a fresh copy is checked. Returns the moves."""
        fresh = FastBoard.from_game_state(game)
        if board is not None:
            self.assertEqual(state_of(board), state_of(fresh), f"{tag}: carried board drifted from the game")
        board = fresh

        self.assertEqual(board.key, board.key_of_engine_position(game._position_keys[-1]), f"{tag}: fingerprint")
        for colour, name in ((0, "white"), (8, "black")):
            self.assertEqual(board.in_check(colour), game.is_in_check(name), f"{tag}: check {name}")
        for colour, name in ((0, "white"), (1, "black")):
            self.assertEqual(board.insufficient(colour), game.has_insufficient_material(name), f"{tag}: material {name}")
        self.assertEqual(board.repetitions() >= 2, game.is_threefold_repetition(), f"{tag}: repetition")

        moves = board.legal_moves()
        described = [board.describe(move) for move in moves]
        self.assertEqual(len(described), len(set(described)), f"{tag}: duplicate moves")
        self.assertEqual(sorted({(a, b) for a, b, _ in described}), engine_moves(game), f"{tag}: legal moves")
        # A promoting pawn has exactly four choices
        for move in moves:
            if move_promotion(move):
                a, b, _ = board.describe(move)
                self.assertEqual(sorted(p for x, y, p in described if (x, y) == (a, b)),
                                 ["Bishop", "Knight", "Queen", "Rook"], f"{tag}: promotion choices")

        # Making and taking back any move must leave no trace, and the quick checks the
        # search relies on must agree with the thorough ones
        before = state_of(board)
        was_in_check = board.in_check()
        mover = board.side
        for move in board.pseudo_moves():
            board.make(move)
            exposed = board.in_check(mover)
            self.assertEqual(board.exposes_king(move, was_in_check), exposed, f"{tag}: exposes_king {board.describe(move)}")
            self.assertEqual(move in moves, not exposed, f"{tag}: legality of {board.describe(move)}")
            if not exposed:
                self.assertEqual(board.gives_check(move), board.in_check(), f"{tag}: gives_check {board.describe(move)}")
            board.unmake()
            self.assertEqual(state_of(board), before, f"{tag}: make/unmake of {board.describe(move)}")
        # captures(): every capture and every promotion, promoting to a queen only
        noisy = [m for m in moves
                 if (board.cells[(m >> 9) & 511] or m >> 21 == 2 or move_promotion(m)) and move_promotion(m) in (0, 5)]
        self.assertEqual(sorted(m for m in board.captures() if m in moves), sorted(noisy), f"{tag}: captures()")
        return moves

    def play(self, game, board, move):
        """Play one FastBoard move on both boards"""
        from_coord, to_coord, promotion = board.describe(move)
        mover = game.current_player
        game.make_move(from_coord, to_coord)
        if game.pending_promotion is not None:
            game.promote_pawn(to_coord, PIECES[promotion](mover))
        board.make(move)

    def play_out(self, game, rng, plies, tag):
        board = FastBoard.from_game_state(game)
        for ply in range(plies):
            moves = self.assert_same_position(game, f"{tag} ply {ply}", board)
            if not moves:
                break
            # Favour captures, promotions and pawn moves: they exercise the rare rules
            sharp = [m for m in moves
                     if game.board.get_piece(board.describe(m)[1]) is not None or move_promotion(m)
                     or isinstance(game.board.get_piece(board.describe(m)[0]), Pawn)]
            rare = [m for m in moves if m >> 21 in (2, 3)]  # en passant and castling
            if rare and rng.random() < 0.7:
                self.play(game, board, rng.choice(rare))
            else:
                self.play(game, board, rng.choice(sharp if sharp and rng.random() < 0.6 else moves))


class TestAgainstTheEngine(FastBoardTestCase):
    def test_starting_position(self):
        moves = self.assert_same_position(GameState(), "start")
        self.assertEqual(len(moves), 157)

    def test_random_games_from_the_starting_position(self):
        for seed in range(4):
            self.play_out(GameState(), random.Random(seed), 70, f"game seed {seed}")

    def test_random_positions(self):
        """Scattered pieces on the full board, with and without rocks, then a few moves each"""
        for seed in range(40):
            rng = random.Random(1000 + seed)
            game = self.random_game(rng, 8, -2, 2, rocks=seed % 2 == 0, count=rng.randint(4, 22))
            if game is not None:
                self.play_out(game, rng, 6, f"position seed {seed}")

    def test_random_positions_on_small_boards(self):
        for seed in range(40):
            rng = random.Random(2000 + seed)
            size, z_min, z_max = rng.choice([(5, -1, 1), (4, 0, 1), (4, -2, 2), (6, -1, 0), (5, 0, 0), (7, 0, 2)])
            game = self.random_game(rng, size, z_min, z_max, rocks=False, count=rng.randint(3, 12))
            if game is not None:
                self.play_out(game, rng, 8, f"small board seed {seed} ({size}, {z_min}, {z_max})")

    def test_pawn_races(self):
        """Many pawns on their home ranks facing advanced enemy pawns: double steps, en passant
        on every layer, and promotions"""
        for seed in range(30):
            rng = random.Random(3000 + seed)
            pieces = [{"coord": (4, 0, 0), "type": "King", "color": "white"},
                      {"coord": (4, 7, 0), "type": "King", "color": "black"}]
            used = {(4, 0, 0), (4, 7, 0)}
            for x in rng.sample(range(8), 5):
                pieces.append({"coord": (x, 1, 0), "type": "Pawn", "color": "white"})
                pieces.append({"coord": (x, 6, 0), "type": "Pawn", "color": "black"})
                used |= {(x, 1, 0), (x, 6, 0)}
            for color, ranks in (("black", (2, 3)), ("white", (4, 5))):
                for _ in range(6):
                    coord = (rng.randrange(8), rng.choice(ranks), rng.choice((-2, -1, 0, 0, 1, 2)))
                    if coord not in used:
                        used.add(coord)
                        pieces.append({"coord": coord, "type": "Pawn", "color": color})
            manager = GameManager()
            response = manager.setup_position(pieces, rng.choice(("white", "black")), rocks=False)
            self.assertTrue(response["success"], response.get("error"))
            if not manager.game.is_in_check("white") and not manager.game.is_in_check("black"):
                self.play_out(manager.game, rng, 14, f"pawn race seed {seed}")

    def test_castling_positions(self):
        """Kings and rooks at home with random pieces around: castling must match exactly"""
        castled = 0
        for seed in range(60):
            rng = random.Random(4000 + seed)
            pieces = [{"coord": (4, 0, 0), "type": "King", "color": "white"},
                      {"coord": (4, 7, 0), "type": "King", "color": "black"}]
            used = {(4, 0, 0), (4, 7, 0)}
            for coord, color in (((0, 0, 0), "white"), ((7, 0, 0), "white"), ((0, 7, 0), "black"), ((7, 7, 0), "black")):
                if rng.random() < 0.85:
                    pieces.append({"coord": coord, "type": "Rook", "color": color})
                    used.add(coord)
            for _ in range(rng.randint(0, 7)):
                coord = (rng.randrange(8), rng.randrange(8), rng.choice((-1, 0, 0, 0, 1)))
                if coord not in used:
                    used.add(coord)
                    pieces.append({"coord": coord, "type": rng.choice(["Queen", "Rook", "Bishop", "Knight", "Pawn"]),
                                   "color": rng.choice(("white", "black"))})
            manager = GameManager()
            player = rng.choice(("white", "black"))
            self.assertTrue(manager.setup_position(pieces, player, rocks=False)["success"])
            game = manager.game
            if game.is_in_check("black" if player == "white" else "white"):
                continue  # the player to move could take the king: not a real position
            board = FastBoard.from_game_state(game)
            moves = self.assert_same_position(game, f"castling seed {seed}", board)
            castles = [m for m in moves if m >> 21 == 3]
            for move in castles:
                castled += 1
                self.play(game, board, move)
                self.assert_same_position(game, f"castling seed {seed} after castling", board)
                game.undo_move()
                board.unmake()
            self.play_out(game, rng, 4, f"castling seed {seed}")
        self.assertGreater(castled, 20, "the castling test hardly castled")

    @staticmethod
    def random_game(rng, size, z_min, z_max, rocks, count):
        """A random legal-looking position built the way the game manager builds them, or None"""
        squares = [(x, y, z) for x in range(size) for y in range(size) for z in range(z_min, z_max + 1)]
        probe = GameManager()
        probe.setup_position([], rocks=rocks, size=size, z_min=z_min, z_max=z_max)
        free = [coord for coord in squares if probe.game.board.get_piece(coord) is None]
        rng.shuffle(free)
        pieces = [{"coord": free.pop(), "type": "King", "color": "white"},
                  {"coord": free.pop(), "type": "King", "color": "black"}]
        for _ in range(count):
            kind = rng.choice(["Queen", "Rook", "Rook", "Bishop", "Bishop", "Knight", "Knight", "Pawn", "Pawn", "Pawn"])
            color = rng.choice(("white", "black"))
            coord = free.pop()
            # A pawn never stands on the rank it promotes on
            if kind == "Pawn" and coord[1] == (size - 1 if color == "white" else 0):
                continue
            pieces.append({"coord": coord, "type": kind, "color": color})
        manager = GameManager()
        player = rng.choice(("white", "black"))
        manager.setup_position(pieces, player, rocks=rocks, size=size, z_min=z_min, z_max=z_max)
        game = manager.game
        # Skip positions where the side that just moved left its king attacked, or kings touch
        if game.is_in_check("black" if player == "white" else "white"):
            return None
        return game


class TestFastBoardOnItsOwn(unittest.TestCase):
    def test_practice_positions_without_kings(self):
        game = GameState(size=5, z_min=-1, z_max=1)
        game.board.set_piece(Knight("white"), (2, 2, 0))
        game.board.set_piece(Bishop("black"), (0, 0, 0))
        game.reset_tracking()
        board = FastBoard.from_game_state(game)
        self.assertEqual(sorted(board.describe(m)[1] for m in board.legal_moves()),
                         sorted(game.get_legal_moves((2, 2, 0))))
        self.assertFalse(board.in_check())

    def test_find_move(self):
        board = FastBoard.from_game_state(GameState())
        move = board.find_move((4, 1, 0), (4, 3, 0))
        self.assertEqual(board.describe(move), ((4, 1, 0), (4, 3, 0), None))
        self.assertIsNone(board.find_move((4, 1, 0), (4, 4, 0)))

    def test_refuses_a_half_finished_turn(self):
        game = GameState()
        game.board.board = {}
        for coord, piece in {(0, 0, 0): King("white"), (7, 7, 2): King("black"), (3, 6, 0): Pawn("white")}.items():
            game.board.set_piece(piece, coord)
        game.reset_tracking()
        game.make_move((3, 6, 0), (3, 7, 0))
        with self.assertRaises(ValueError):
            FastBoard.from_game_state(game)

    def test_score_is_symmetric_at_the_start(self):
        board = FastBoard.from_game_state(GameState())
        self.assertEqual(board.score, 0)


if __name__ == '__main__':
    unittest.main()
