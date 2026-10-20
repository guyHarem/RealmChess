"""
Clouds: shelter above the Ground. A piece in a cloud can't be captured (or blown up), but it
can't capture or give check either. Kings can't enter. Sliding pieces can't pass through.
"""
import unittest

from engine.game_state import GameState
from engine.pieces import Bishop, King, Knight, Pawn, Queen, Rook
from tests.test_game_state import custom_game

KINGS = {(4, 0, 0): King("white"), (4, 7, 0): King("black")}


def cloud_game(pieces, clouds, current_player="white", dynamite=()):
    game = custom_game({**KINGS, **pieces}, current_player, rocks=False)
    # A piece already sheltering in a cloud is set up on its cell after the clouds
    sheltered = {cell: game.board.board.pop(cell) for cell in clouds if cell in game.board.board}
    game.board.set_clouds(clouds)
    game.board.board.update(sheltered)
    if dynamite:
        game.board.set_dynamite(dynamite)
    game.reset_tracking()
    return game


class TestShelter(unittest.TestCase):
    def test_a_piece_may_enter_an_empty_cloud(self):
        game = cloud_game({(0, 0, 1): Rook("white")}, [(0, 3, 1)])
        self.assertIn((0, 3, 1), game.get_legal_moves((0, 0, 1)))

    def test_sliders_cannot_pass_through_a_cloud(self):
        game = cloud_game({(0, 0, 1): Rook("white")}, [(0, 3, 1)])
        self.assertNotIn((0, 4, 1), game.get_legal_moves((0, 0, 1)))
        self.assertIn((0, 2, 1), game.get_legal_moves((0, 0, 1)))

    def test_knights_jump_over_clouds(self):
        game = cloud_game({(1, 0, 1): Knight("white")}, [(1, 1, 1), (0, 1, 1)])
        self.assertIn((2, 2, 1), game.get_legal_moves((1, 0, 1)))

    def test_nothing_in_a_cloud_can_be_captured(self):
        game = cloud_game({(0, 0, 1): Rook("white"), (0, 3, 1): Knight("black")}, [(0, 3, 1)])
        self.assertNotIn((0, 3, 1), game.get_legal_moves((0, 0, 1)))
        pawn = cloud_game({(1, 2, 1): Pawn("white"), (2, 3, 1): Knight("black")}, [(2, 3, 1)])
        self.assertNotIn((2, 3, 1), pawn.get_legal_moves((1, 2, 1)))

    def test_nothing_in_a_cloud_can_capture(self):
        game = cloud_game({(0, 3, 1): Rook("white"), (0, 6, 1): Knight("black")}, [(0, 3, 1)])
        moves = game.get_legal_moves((0, 3, 1))
        self.assertNotIn((0, 6, 1), moves)
        self.assertIn((0, 5, 1), moves)       # it can still leave for an empty cell

    def test_a_piece_in_a_cloud_gives_no_check(self):
        game = cloud_game({(4, 3, 1): Queen("white")}, [(4, 3, 1)], current_player="black")
        game.board.remove_piece((4, 7, 0))
        game.board.set_piece(King("black"), (4, 6, 1))
        game.black_king_pos = (4, 6, 1)
        self.assertFalse(game.is_in_check("black"))
        # ... and the king may step where only the sheltered queen points
        self.assertIn((4, 5, 1), game.get_legal_moves((4, 6, 1)))

    def test_a_cloud_shields_a_king_from_a_line(self):
        game = cloud_game({(4, 2, 0): Rook("black")}, [], current_player="white")
        self.assertTrue(game.is_in_check("white"))
        sky = cloud_game({(4, 0, 2): Rook("black")}, [(4, 0, 1)])
        self.assertFalse(sky.is_in_check("white"))   # the rook in Space is cut off by the Sky cloud

    def test_kings_cannot_enter(self):
        game = cloud_game({}, [(4, 0, 1)])
        self.assertNotIn((4, 0, 1), game.get_legal_moves((4, 0, 0)))

    def test_a_cloud_shelters_from_a_blast(self):
        game = cloud_game({(0, 4, 1): Rook("white"), (3, 4, 1): Bishop("black"), (2, 5, 1): Knight("black")},
                          [(3, 4, 1)], dynamite=[(2, 4, 1)])
        game.make_move((0, 4, 1), (2, 4, 1))
        self.assertIsInstance(game.board.get_piece((3, 4, 1)), Bishop)   # in the cloud: unharmed
        self.assertIsNone(game.board.get_piece((2, 5, 1)))

    def test_no_en_passant_into_or_out_of_a_cloud(self):
        game = cloud_game({(3, 1, 0): Pawn("white"), (4, 3, 1): Pawn("black")}, [(4, 3, 1)], current_player="white")
        game.make_move((3, 1, 0), (3, 3, 0))
        game.current_player = "black"
        self.assertEqual(game.get_en_passant_moves((4, 3, 1)), [])


class TestLayout(unittest.TestCase):
    def test_clouds_only_above_the_ground_on_empty_cells(self):
        game = GameState()
        for cells in ([(3, 3, 0)], [(3, 3, -1)], [(0, 0, 0)]):
            with self.assertRaises(ValueError):
                game.board.set_clouds(cells)
        game.board.set_dynamite([(3, 3, 1)])
        with self.assertRaises(ValueError):
            game.board.set_clouds([(3, 3, 1)])
        game.board.set_clouds([(3, 4, 2)])
        self.assertEqual(game.board.clouds, {(3, 4, 2)})


if __name__ == '__main__':
    unittest.main()
