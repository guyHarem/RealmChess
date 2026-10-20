"""
Portals: a piece that ends its move on an empty portal comes out on the other cell of the pair.
"""
import unittest

from engine.game_state import GameState
from engine.pieces import Bishop, King, Knight, Pawn, Queen, Rook
from tests.test_game_state import custom_game

# Two pairs as in the classic layout: Space a4 <-> Abyss h5, Space a5 <-> Abyss h4
A, A2 = (0, 3, 2), (7, 4, -2)
B, B2 = (0, 4, 2), (7, 3, -2)
KINGS = {(4, 0, 0): King("white"), (4, 7, 0): King("black")}


def portal_game(pieces, current_player="white", pairs=((A, A2), (B, B2))):
    game = custom_game({**KINGS, **pieces}, current_player, rocks=False)
    game.board.set_portals(pairs)
    return game


class TestTravel(unittest.TestCase):
    def test_a_piece_ending_on_a_portal_comes_out_of_its_twin(self):
        game = portal_game({(0, 0, 2): Rook("white")})
        self.assertIn(A2, game.get_legal_moves((0, 0, 2)))
        self.assertNotIn(A, game.get_legal_moves((0, 0, 2)))   # nobody stands on an empty portal
        game.make_move((0, 0, 2), A2)
        self.assertIsNone(game.board.get_piece(A))
        self.assertIsInstance(game.board.get_piece(A2), Rook)
        entry = game.move_history[-1]
        self.assertEqual((entry["special_move"], entry["via"]), ("portal", A))

    def test_sliders_cannot_pass_over_an_empty_portal(self):
        game = portal_game({(0, 0, 2): Rook("white")})
        moves = game.get_legal_moves((0, 0, 2))
        self.assertIn((0, 2, 2), moves)
        self.assertNotIn((0, 5, 2), moves)   # beyond the portal on the a file

    def test_landing_captures_an_enemy_but_never_a_friend(self):
        game = portal_game({(0, 0, 2): Rook("white"), A2: Knight("black")})
        self.assertIn(A2, game.get_legal_moves((0, 0, 2)))
        game.make_move((0, 0, 2), A2)
        self.assertEqual(game.move_history[-1]["captured_piece"], "Knight(black)")
        friend = portal_game({(0, 0, 2): Rook("white"), A2: Knight("white")})
        self.assertNotIn(A2, friend.get_legal_moves((0, 0, 2)))

    def test_a_piece_on_a_portal_plugs_it(self):
        # The black knight came through to A; the rook can only capture it there
        game = portal_game({(0, 0, 2): Rook("white"), A: Knight("black")})
        moves = game.get_legal_moves((0, 0, 2))
        self.assertIn(A, moves)
        self.assertNotIn(A2, moves)
        # ... and leaving a portal is an ordinary move, not a trip back
        knight = portal_game({A: Knight("white")})
        self.assertNotIn(A, knight.get_legal_moves(A))

    def test_knights_and_kings_travel_too(self):
        game = portal_game({(1, 1, 2): Knight("white")})   # a knight jump away from A (0,3,2)
        self.assertIn(A2, game.get_legal_moves((1, 1, 2)))
        king = portal_game({}, pairs=(((4, 1, 0), (2, 5, -1)),))
        self.assertIn((2, 5, -1), king.get_legal_moves((4, 0, 0)))

    def test_pawns_step_through_to_an_empty_cell_and_capture_through_to_an_enemy(self):
        game = portal_game({(0, 2, 2): Pawn("white")})
        self.assertIn(A2, game.get_legal_moves((0, 2, 2)))          # a step onto A
        blocked = portal_game({(0, 2, 2): Pawn("white"), A2: Knight("black")})
        self.assertNotIn(A2, blocked.get_legal_moves((0, 2, 2)))    # a step never captures
        capture = portal_game({(1, 2, 2): Pawn("white"), A2: Knight("black")})
        self.assertIn(A2, capture.get_legal_moves((1, 2, 2)))       # a diagonal onto A captures at A2
        empty = portal_game({(1, 2, 2): Pawn("white")})
        self.assertNotIn(A2, empty.get_legal_moves((1, 2, 2)))

    def test_a_double_step_cannot_jump_over_a_portal(self):
        game = portal_game({(0, 1, 2): Pawn("white")}, pairs=(((0, 2, 2), (5, 5, 1)),))
        self.assertNotIn((0, 3, 2), game.get_legal_moves((0, 1, 2)))
        self.assertIn((5, 5, 1), game.get_legal_moves((0, 1, 2)))

    def test_a_pawn_arriving_on_the_last_rank_promotes(self):
        game = portal_game({(3, 5, 1): Pawn("white")}, pairs=(((3, 6, 1), (5, 7, 2)),))
        game.make_move((3, 5, 1), (5, 7, 2))
        self.assertEqual(game.pending_promotion, (5, 7, 2))

    def test_no_en_passant_after_a_trip(self):
        game = portal_game({(0, 1, 2): Pawn("white"), (1, 3, -2): Pawn("black")},
                           pairs=(((0, 3, 2), (0, 3, -2)),))
        game.make_move((0, 1, 2), (0, 3, -2))
        self.assertIsNone(game.get_en_passant_target())

    def test_taking_back_a_trip(self):
        game = portal_game({(0, 0, 2): Rook("white"), A2: Knight("black")})
        game.make_move((0, 0, 2), A2)
        self.assertTrue(game.undo_move())
        self.assertIsInstance(game.board.get_piece((0, 0, 2)), Rook)
        self.assertIsInstance(game.board.get_piece(A2), Knight)
        self.assertEqual(game.current_player, "white")


class TestCheckThroughPortals(unittest.TestCase):
    def test_a_piece_gives_check_through_a_portal(self):
        # The black king stands on A2's twin side: a rook reaching A attacks A2
        game = portal_game({(0, 0, 2): Rook("white")}, current_player="black")
        game.board.remove_piece((4, 7, 0))
        game.board.set_piece(King("black"), A2)
        game.black_king_pos = A2
        self.assertTrue(game.is_in_check("black"))
        # Plugging the portal ends the check
        game.board.set_piece(Knight("black"), A)
        self.assertFalse(game.is_in_check("black"))

    def test_a_king_may_not_step_where_a_portal_attacks(self):
        game = portal_game({(0, 0, 2): Rook("white"), (6, 5, -2): King("black")}, current_player="black")
        game.board.remove_piece((4, 7, 0))
        game.black_king_pos = (6, 5, -2)
        self.assertNotIn(A2, game.get_legal_moves((6, 5, -2)))

    def test_a_piece_plugging_a_portal_is_pinned_if_its_king_stands_on_the_twin(self):
        # White king on B2; the white bishop on B keeps the black rook (a8 Space) from coming
        # through. Every bishop move would empty B, so it has none.
        game = portal_game({(0, 7, 2): Rook("black"), B: Bishop("white")})
        game.board.remove_piece((4, 0, 0))
        game.board.set_piece(King("white"), B2)
        game.white_king_pos = B2
        self.assertFalse(game.is_in_check("white"))
        self.assertEqual(game.get_legal_moves(B), [])


class TestLayouts(unittest.TestCase):
    def test_portal_cells_must_be_free_of_rocks_and_distinct(self):
        game = GameState()
        with self.assertRaises(ValueError):
            game.board.set_portals([((2, 2, -1), (0, 3, 2))])   # a Dungeon rock
        with self.assertRaises(ValueError):
            game.board.set_portals([(A, A2), (A2, B)])
        game.board.set_portals([(A, A2), (B, B2)])
        self.assertEqual(game.board.portal_pairs(), sorted([tuple(sorted((A, A2))), tuple(sorted((B, B2)))]))


if __name__ == '__main__':
    unittest.main()
