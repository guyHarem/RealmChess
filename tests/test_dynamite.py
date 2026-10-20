"""
Dynamite: a piece that ends its move on it sets it off. Every piece in the 3x3x3 cube around
it is removed, the piece itself too, except kings. Rocks there are destroyed, and other
dynamite there goes off as well.
"""
import unittest

from engine.game_state import GameState
from engine.pieces import Bishop, King, Knight, Pawn, Queen, Rock, Rook
from tests.test_game_state import custom_game

KINGS = {(4, 0, 0): King("white"), (4, 7, 0): King("black")}


def dynamite_game(pieces, charges, current_player="white", rocks=False):
    game = custom_game({**KINGS, **pieces}, current_player, rocks=rocks)
    game.board.set_dynamite(charges)
    game.reset_tracking()
    return game


class TestBlast(unittest.TestCase):
    def test_the_blast_removes_everything_in_the_cube_and_the_mover(self):
        game = dynamite_game({(0, 4, 0): Rook("white"), (3, 3, 1): Knight("black"), (4, 5, -1): Bishop("black"),
                              (5, 4, 0): Pawn("black"), (6, 4, 0): Queen("black")}, [(4, 4, 0)])
        self.assertIn((4, 4, 0), game.get_legal_moves((0, 4, 0)))
        game.make_move((0, 4, 0), (4, 4, 0))
        for cell in ((4, 4, 0), (3, 3, 1), (4, 5, -1), (5, 4, 0)):
            self.assertIsNone(game.board.get_piece(cell), cell)
        self.assertIsInstance(game.board.get_piece((6, 4, 0)), Queen)   # two cells away: safe
        self.assertEqual(game.board.dynamite, set())
        entry = game.move_history[-1]
        self.assertEqual(entry["special_move"], "explosion")
        self.assertEqual(sorted(text for _, text in entry["blast"]),
                         ["Bishop(black)", "Knight(black)", "Pawn(black)", "Rook(white)"])
        self.assertEqual(entry["charges"], [(4, 4, 0)])
        self.assertEqual(game.halfmove_clock, 0)

    def test_kings_survive(self):
        game = dynamite_game({(3, 1, 0): Knight("white")}, [(4, 1, 0)])
        game.make_move((4, 0, 0), (4, 1, 0))     # the king itself steps on it
        self.assertIsInstance(game.board.get_piece((4, 1, 0)), King)
        self.assertIsNone(game.board.get_piece((3, 1, 0)))
        self.assertEqual(game.white_king_pos, (4, 1, 0))

    def test_rocks_are_destroyed(self):
        game = dynamite_game({(1, 3, -1): Rook("white")}, [(2, 3, -1)], rocks=True)
        self.assertIsInstance(game.board.get_piece((2, 2, -1)), Rock)
        game.make_move((1, 3, -1), (2, 3, -1))
        self.assertIsNone(game.board.get_piece((2, 2, -1)))
        self.assertIsNone(game.board.get_piece((3, 3, -1)))
        self.assertIsNone(game.board.get_piece((3, 2, -2)))              # one layer down: also gone
        self.assertIsInstance(game.board.get_piece((5, 3, -2)), Rock)    # outside the cube: untouched

    def test_one_blast_sets_off_the_next(self):
        game = dynamite_game({(0, 4, 0): Rook("white"), (5, 5, 0): Knight("black")}, [(3, 4, 0), (4, 4, 0)])
        game.make_move((0, 4, 0), (3, 4, 0))
        self.assertEqual(game.board.dynamite, set())
        self.assertIsNone(game.board.get_piece((5, 5, 0)))   # reached only by the second blast
        self.assertEqual(sorted(game.move_history[-1]["charges"]), [(3, 4, 0), (4, 4, 0)])

    def test_passing_over_dynamite_does_nothing(self):
        game = dynamite_game({(0, 4, 0): Rook("white"), (3, 3, 0): Knight("black")}, [(2, 4, 0)])
        game.make_move((0, 4, 0), (5, 4, 0))
        self.assertEqual(game.board.dynamite, {(2, 4, 0)})
        self.assertIsInstance(game.board.get_piece((3, 3, 0)), Knight)

    def test_a_pawn_cannot_capture_onto_dynamite_but_may_step_on_it(self):
        game = dynamite_game({(3, 2, 0): Pawn("white")}, [(3, 3, 0), (4, 3, 0)])
        moves = game.get_legal_moves((3, 2, 0))
        self.assertIn((3, 3, 0), moves)
        self.assertNotIn((4, 3, 0), moves)

    def test_a_pawn_blown_up_on_the_last_rank_does_not_promote(self):
        game = dynamite_game({(0, 6, 0): Pawn("white")}, [(0, 7, 0)])
        game.make_move((0, 6, 0), (0, 7, 0))
        self.assertIsNone(game.pending_promotion)
        self.assertIsNone(game.board.get_piece((0, 7, 0)))
        self.assertEqual(game.current_player, "black")

    def test_a_blast_that_uncovers_your_own_king_is_not_allowed(self):
        # The white knight shields its king from the rook; blowing it up would expose the king
        game = dynamite_game({(4, 2, 0): Knight("white"), (4, 5, 0): Rook("black"), (0, 3, 0): Bishop("white")},
                             [(4, 3, 0)])
        game.board.remove_piece((4, 0, 0))
        game.board.set_piece(King("white"), (4, 1, 0))
        game.white_king_pos = (4, 1, 0)
        self.assertNotIn((4, 3, 0), game.get_legal_moves((0, 3, 0)) + game.get_legal_moves((4, 2, 0)))

    def test_a_blast_can_uncover_check_on_the_enemy(self):
        # The white rook on e3 is outside the blast; the black knight on e6 shields the king
        game = dynamite_game({(4, 2, 0): Rook("white"), (4, 5, 0): Knight("black"), (0, 4, 0): Rook("white")},
                             [(4, 4, 0)])
        game.make_move((0, 4, 0), (4, 4, 0))
        self.assertTrue(game.is_in_check("black"))   # the knight is gone from the e file

    def test_taking_back_a_blast_restores_everything(self):
        game = dynamite_game({(0, 4, 0): Rook("white"), (3, 3, 1): Knight("black"), (1, 3, -1): Rook("black")},
                             [(2, 4, 0), (2, 3, -1)], rocks=True)
        before = (dict(game.board.board), set(game.board.dynamite), game._position_keys[-1])
        game.make_move((0, 4, 0), (2, 4, 0))
        self.assertTrue(game.undo_move())
        self.assertEqual((dict(game.board.board), set(game.board.dynamite), game._position_keys[-1]), before)
        self.assertEqual(game.current_player, "white")

    def test_dynamite_left_counts_for_repetition(self):
        game = dynamite_game({}, [(0, 3, 0)])
        key = game._position_keys[-1]
        game.board.dynamite.clear()
        self.assertNotEqual(game._position_key(), key)


class TestLayout(unittest.TestCase):
    def test_dynamite_needs_an_empty_cell_that_is_not_a_portal(self):
        game = GameState()
        with self.assertRaises(ValueError):
            game.board.set_dynamite([(0, 0, 0)])
        game.board.set_portals([((0, 3, 1), (7, 4, -1))])
        with self.assertRaises(ValueError):
            game.board.set_dynamite([(0, 3, 1)])
        game.board.set_dynamite([(3, 3, 1)])
        self.assertEqual(game.board.dynamite, {(3, 3, 1)})

    def test_the_blast_area_stops_at_the_edges(self):
        board = GameState().board
        self.assertEqual(len(board.blast_area((4, 4, 0))), 27)
        self.assertEqual(len(board.blast_area((0, 0, 2))), 8)


if __name__ == '__main__':
    unittest.main()
