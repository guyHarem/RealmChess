"""
The computer player: does it find what it should, at every level, within its limits?

The puzzles in realmchess-frontend/src/scenarios.json each have exactly one solution, so they
make a ready-made exam: the hard level must solve all of them.
"""
import json
import os
import random
import time
import unittest

from ai.board import FastBoard
from ai.evaluate import DEFAULT_PARAMS, MATE, cornering, position_features
from ai.levels import LEVELS, accepts_draw, choose_move, think_time
from ai.search import Search
from api.game_manager import GameManager
from engine import pieces
from engine.game_state import GameState
from engine.pieces import King, Queen, Rook, Knight, Pawn
from tests.test_fast_board import state_of

SCENARIOS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "realmchess-frontend", "src", "scenarios.json")


def position(placed, current_player="white", size=8, z_min=-2, z_max=2):
    """A game from {coord: piece}, built without rocks"""
    game = GameState(size=size, z_min=z_min, z_max=z_max)
    game.board.board = {}
    for coord, piece in placed.items():
        if hasattr(piece, "has_moved"):
            piece.has_moved = True
        game.board.set_piece(piece, coord)
    game.current_player = current_player
    game.reset_tracking()
    return game


class TestPuzzles(unittest.TestCase):
    def test_hard_solves_every_scenario(self):
        with open(SCENARIOS_PATH, encoding="utf-8") as f:
            tiers = json.load(f)["tiers"]
        count = 0
        for tier in tiers:
            for scenario in tier["scenarios"]:
                with self.subTest(scenario["id"]):
                    manager = GameManager()
                    placed = [{"coord": tuple(p["coord"]), "type": p["type"], "color": p.get("color")}
                              for p in scenario["pieces"]]
                    board_size = tier["board"]
                    manager.setup_position(placed, "white", rocks=tier["rocks"], size=board_size["size"],
                                           z_min=board_size["z_min"], z_max=board_size["z_max"])
                    choice = choose_move(manager.game, "hard")
                    key = scenario["solution"]["key"]
                    self.assertEqual((choice.from_coord, choice.to_coord), (tuple(key["from"]), tuple(key["to"])))
                    self.assertEqual(choice.mate_in, tier["mateIn"])
                    self.assertLess(choice.seconds, 2.0)
                    count += 1
        self.assertEqual(count, 32)


class TestCommonSense(unittest.TestCase):
    def test_every_level_takes_a_free_queen(self):
        for level in LEVELS:
            game = position({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                             (0, 3, 0): Rook("white"), (6, 3, 0): Queen("black"), (1, 6, 1): Pawn("black")})
            for seed in range(5):
                choice = choose_move(game, level, seconds=0.3, rng=random.Random(seed))
                self.assertEqual((choice.from_coord, choice.to_coord), ((0, 3, 0), (6, 3, 0)), level)

    def test_medium_and_hard_do_not_leave_the_queen_to_be_taken(self):
        for level in ("medium", "hard"):
            for seed in range(4):
                game = position({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                 (3, 3, 0): Queen("white"), (3, 6, 0): Rook("black"),
                                 (0, 6, 0): Pawn("black"), (7, 1, 0): Pawn("white")})
                choice = choose_move(game, level, seconds=0.3, rng=random.Random(seed))
                game.make_move(choice.from_coord, choice.to_coord)
                queen = next(coord for coord, piece in game.board.board.items() if isinstance(piece, Queen))
                attackers = [coord for coord, _ in game.get_all_pieces_of_color("black")
                             if queen in game.get_legal_moves(coord)]
                self.assertEqual(attackers, [], f"{level} left the queen on {queen} to be taken")

    def test_prefers_checkmate_to_winning_material(self):
        # The rook mates on the last rank of a flat board; a black knight is also free to take
        game = position({(0, 4, 0): King("black"), (0, 2, 0): King("white"),
                         (4, 3, 0): Rook("white"), (4, 0, 0): Knight("black")}, size=5, z_min=0, z_max=0)
        choice = choose_move(game, "hard")
        self.assertEqual((choice.from_coord, choice.to_coord), ((4, 3, 0), (4, 4, 0)))
        self.assertEqual(choice.mate_in, 1)

    def test_no_move_when_the_game_is_over(self):
        game = position({(0, 4, 0): King("black"), (0, 2, 0): King("white"), (4, 4, 0): Rook("white")},
                        current_player="black", size=5, z_min=0, z_max=0)
        self.assertTrue(game.is_checkmate("black"))
        self.assertIsNone(choose_move(game, "hard"))

    def test_promotes_a_pawn(self):
        game = position({(0, 0, 0): King("white"), (7, 7, 2): King("black"), (3, 6, 0): Pawn("white")})
        choice = choose_move(game, "hard", seconds=0.3)
        self.assertEqual(choice.from_coord, (3, 6, 0))
        self.assertEqual(choice.promotion, "Queen")

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            choose_move(GameState(), "impossible")


class TestLimits(unittest.TestCase):
    def test_hard_keeps_to_its_time(self):
        started = time.perf_counter()
        choice = choose_move(GameState(), "hard", seconds=0.4)
        self.assertLess(time.perf_counter() - started, 0.9)
        self.assertGreaterEqual(choice.depth, 2)

    def test_easy_and_medium_look_a_fixed_distance_ahead(self):
        self.assertEqual(choose_move(GameState(), "easy").depth, 1)
        self.assertEqual(choose_move(GameState(), "medium").depth, 2)

    def test_weaker_levels_vary_their_play(self):
        for level in ("easy", "medium"):
            moves = {(c.from_coord, c.to_coord)
                     for c in (choose_move(GameState(), level, rng=random.Random(seed)) for seed in range(12))}
            self.assertGreater(len(moves), 2, level)

    def test_searching_leaves_the_board_untouched(self):
        board = FastBoard.from_game_state(GameState())
        before = state_of(board)
        Search(board).run(max_depth=3)
        self.assertEqual(state_of(board), before)
        Search(board).run(nodes=3000)          # cut off in mid-search
        self.assertEqual(state_of(board), before)
        Search(board).run(seconds=0.05)
        self.assertEqual(state_of(board), before)

    def test_a_node_budget_gives_the_same_answer_every_time(self):
        first = Search(FastBoard.from_game_state(GameState())).run(nodes=20000)
        second = Search(FastBoard.from_game_state(GameState())).run(nodes=20000)
        self.assertEqual((first.move, first.score, first.depth), (second.move, second.score, second.depth))

    def test_think_time_shrinks_when_the_clock_is_low(self):
        self.assertEqual(think_time("hard"), 3.0)
        self.assertEqual(think_time("hard", clock_left=600, increment=0), 3.0)
        self.assertAlmostEqual(think_time("hard", clock_left=25, increment=0), 1.0)
        self.assertAlmostEqual(think_time("hard", clock_left=0.2, increment=0), 0.05)
        self.assertIsNone(think_time("easy", clock_left=5))


class TestWholeGames(unittest.TestCase):
    def test_each_level_plays_legal_moves_to_the_end(self):
        """Every level against itself for a while, refereed by the real game manager"""
        for level in LEVELS:
            rng = random.Random(7)
            manager = GameManager()
            for ply in range(40):
                color = manager.game.current_player
                choice = choose_move(manager.game, level, seconds=0.1, rng=rng)
                response = manager.make_move(choice.from_coord, choice.to_coord)
                self.assertTrue(response["success"], f"{level} ply {ply}: {response.get('error')}")
                if response["pending_promotion"] is not None:
                    response = manager.promote_pawn(choice.to_coord, getattr(pieces, choice.promotion)(color))
                    self.assertTrue(response["success"])
                if response["status"] not in ("ongoing", "check"):
                    break


class TestDrawOffers(unittest.TestCase):
    def test_declines_at_the_start(self):
        self.assertFalse(accepts_draw(GameState(), "black"))

    def test_accepts_when_clearly_worse(self):
        game = position({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                         (3, 0, 0): Queen("white"), (0, 0, 0): Rook("white"), (6, 7, 0): Knight("black")})
        self.assertTrue(accepts_draw(game, "black"))
        self.assertFalse(accepts_draw(game, "white"))


class TestScoringParameters(unittest.TestCase):
    """The scoring numbers are named parameters, so that tools/tune.py can fit them"""

    def test_the_score_is_the_features_times_the_parameters(self):
        rng = random.Random(3)
        game = GameState()
        for ply in range(40):
            board = FastBoard.from_game_state(game)
            features = position_features(board)
            expected = sum(DEFAULT_PARAMS[name] * amount for name, amount in features.items())
            # Each piece's placement and closeness values are rounded to whole numbers, so
            # allow a point per piece
            pieces_on_board = len(board.squares[0]) + len(board.squares[1])
            self.assertAlmostEqual(board.score + cornering(board), expected, delta=pieces_on_board + 0.01,
                                   msg=f"ply {ply}")
            move = rng.choice(board.legal_moves())
            from_coord, to_coord, promotion = board.describe(move)
            game.make_move(from_coord, to_coord)
            if game.pending_promotion is not None:
                game.promote_pawn(to_coord, Queen("white" if ply % 2 == 0 else "black"))

    def test_other_parameters_give_other_scores_without_disturbing_the_defaults(self):
        game = position({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                         (3, 0, 0): Queen("white"), (0, 7, 0): Rook("black"), (7, 7, 0): Rook("black")})
        usual = FastBoard.from_game_state(game).score
        queen_lover = FastBoard.from_game_state(game, {**DEFAULT_PARAMS, "queen": DEFAULT_PARAMS["queen"] + 300}).score
        self.assertEqual(queen_lover, usual + 300)
        self.assertEqual(FastBoard.from_game_state(game).score, usual)

    def test_parameters_change_what_the_computer_plays(self):
        # A rook and a knight are both free to take; which one depends on what they are worth
        game = position({(4, 0, 0): King("white"), (4, 7, 0): King("black"), (0, 3, 0): Queen("white"),
                         (0, 6, 0): Rook("black"), (3, 3, 0): Knight("black")})
        takes = {}
        for name in ("rook", "knight"):
            params = {**DEFAULT_PARAMS, "rook": 300, "knight": 300, name: 900}
            choice = choose_move(game, "medium", rng=random.Random(1), params=params)
            takes[name] = choice.to_coord
        self.assertEqual(takes, {"rook": (0, 6, 0), "knight": (3, 3, 0)})


class TestCorneringTheKing(unittest.TestCase):
    """Two scoring terms give the computer a sense of closing in: pieces near the enemy king,
    and, against a bare king, how few exits it has and how close the attacker's king is"""

    def corner(self, placed, **keywords):
        return cornering(FastBoard.from_game_state(position(placed, **keywords)))

    def test_only_applies_against_a_bare_king(self):
        self.assertEqual(cornering(FastBoard.from_game_state(GameState())), 0)
        both_have_pieces = {(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (3, 0, 0): Queen("white"), (0, 7, 0): Knight("black")}
        self.assertEqual(self.corner(both_have_pieces), 0)

    def test_fewer_exits_and_a_closer_king_score_higher(self):
        def score(black_king, white_king=(4, 0, 0)):
            return self.corner({white_king: King("white"), black_king: King("black"), (0, 3, 1): Queen("white")})
        open_board, edge, corner = score((4, 4, 0)), score((4, 7, 0)), score((7, 7, 2))
        self.assertGreater(open_board, 0)
        self.assertGreater(edge, open_board + 70 * 3 - 35 * 3 - 1)   # three exits fewer, three steps further
        self.assertGreater(corner, edge)
        self.assertGreater(score((7, 7, 2), white_king=(5, 5, 2)), corner)

    def test_it_is_the_attackers_bonus_whichever_color_attacks(self):
        white_attacks = self.corner({(4, 0, 0): King("white"), (7, 7, 2): King("black"), (0, 3, 1): Queen("white")})
        black_attacks = self.corner({(4, 7, 0): King("black"), (7, 0, 2): King("white"), (0, 4, 1): Queen("black")})
        self.assertEqual(white_attacks, -black_attacks)

    def test_no_bonus_for_pieces_that_can_never_mate(self):
        lone_rook = {(4, 0, 0): King("white"), (7, 7, 2): King("black"), (0, 3, 1): Rook("white")}
        self.assertEqual(self.corner(lone_rook), 0)

    def test_a_rock_counts_as_a_lost_exit(self):
        free = self.corner({(0, 0, 0): King("white"), (3, 3, 2): King("black"), (0, 3, 1): Queen("white")})
        game = position({(0, 0, 0): King("white"), (3, 3, 2): King("black"), (0, 3, 1): Queen("white")})
        game.board.set_piece(pieces.Rock(), (3, 3, 1))   # right under the black king
        self.assertEqual(cornering(FastBoard.from_game_state(game)), free + 70)

    def test_pieces_near_the_enemy_king_score_higher(self):
        def score(queen):
            return FastBoard.from_game_state(position({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                                       queen: Queen("white"), (0, 6, 2): Rook("black")})).score
        # Both squares are on the same layer and reach the same number of squares
        far, near = score((1, 1, 0)), score((6, 6, 0))
        # Two steps from the king against four or more: two steps of closeness
        self.assertEqual(near - far, round(DEFAULT_PARAMS["near_queen"] * 2))
        self.assertGreater(near, far)

    def test_two_queens_mate_a_bare_king(self):
        game = position({(4, 0, 0): King("white"), (4, 7, 2): King("black"),
                         (3, 0, 0): Queen("white"), (5, 0, 0): Queen("white")})
        manager = GameManager()
        manager._replace_game(game)
        response = manager.get_state()
        for ply in range(60):
            board = FastBoard.from_game_state(manager.game)
            from_coord, to_coord, _ = board.describe(Search(board).run(nodes=6000).move)
            response = manager.make_move(from_coord, to_coord)
            self.assertTrue(response["success"], response.get("error"))
            if response["status"] not in ("ongoing", "check"):
                break
        self.assertEqual((response["status"], response["winner"]), ("checkmate", "white"))


class TestScores(unittest.TestCase):
    def test_mate_scores_count_the_moves(self):
        game = position({(0, 4, 0): King("black"), (0, 2, 0): King("white"), (4, 3, 0): Rook("white")},
                        size=5, z_min=0, z_max=0)
        result = Search(FastBoard.from_game_state(game)).run(max_depth=4)
        self.assertEqual(result.score, MATE - 1)
        self.assertEqual(result.mate_in, 1)


if __name__ == '__main__':
    unittest.main()
