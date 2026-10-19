import unittest
from engine.game_state import GameState
from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn, Rock


def custom_game(pieces, current_player="white", rocks=True):
    """Build a game from a {coord: piece} dict (must contain both kings)"""
    game = GameState()
    if rocks:
        game.board.board = {c: p for c, p in game.board.board.items() if isinstance(p, Rock)}
    else:
        game.board.board = {}
    for coord, piece in pieces.items():
        game.board.set_piece(piece, coord)
        if isinstance(piece, King):
            if piece.color == "white":
                game.white_king_pos = coord
            else:
                game.black_king_pos = coord
    game.current_player = current_player
    game.restart_draw_tracking()
    return game


def shuttle(game, moves, times=1):
    """Play a list of (from, to) moves, repeated"""
    for _ in range(times):
        for from_coord, to_coord in moves:
            game.make_move(from_coord, to_coord)


def moved(piece):
    piece.has_moved = True
    return piece


def snapshot(game):
    """Everything that undo must restore"""
    board = {c: (str(p), getattr(p, 'has_moved', None)) for c, p in game.board.board.items()}
    return (board, game.current_player, game.white_king_pos, game.black_king_pos,
            game.pending_promotion, list(game.move_history),
            game.halfmove_clock, list(game._position_keys))


class TestOpeningPosition(unittest.TestCase):
    def setUp(self):
        self.game = GameState()

    def test_king_trackers_point_at_kings(self):
        self.assertIsInstance(self.game.board.get_piece(self.game.white_king_pos), King)
        self.assertIsInstance(self.game.board.get_piece(self.game.black_king_pos), King)

    def test_every_piece_can_be_queried(self):
        for coord in list(self.game.board.board):
            self.game.get_legal_moves(coord)  # must not raise

    def test_not_check_mate_or_draw(self):
        for color in ("white", "black"):
            self.assertFalse(self.game.is_in_check(color))
            self.assertFalse(self.game.is_checkmate(color))
            self.assertFalse(self.game.is_stalemate(color))
        self.assertFalse(self.game.is_draw())

    def test_rook_cannot_jump_over_pieces(self):
        # Hemmed in on its layer, but free to ride the "elevator"
        self.assertEqual(sorted(self.game.get_legal_moves((0, 0, 0))),
                         [(0, 0, -2), (0, 0, -1), (0, 0, 1), (0, 0, 2)])

    def test_bishop_cannot_jump_over_pieces(self):
        # The knight in the Dungeon beside it blocks one of its lines down
        moves = self.game.get_legal_moves((2, 0, 0))
        self.assertEqual(len(moves), 10)
        self.assertTrue(all(z != 0 for _, _, z in moves))

    def test_king_has_only_vertical_moves(self):
        self.assertEqual(sorted(self.game.get_legal_moves((4, 0, 0))), [(4, 0, -1), (4, 0, 1)])

    def test_knight_jumps(self):
        moves = self.game.get_legal_moves((1, 0, 0))
        self.assertIn((2, 2, 0), moves)
        self.assertIn((0, 2, 0), moves)

    def test_white_pawn_moves(self):
        self.assertEqual(sorted(self.game.get_legal_moves((4, 1, 0))),
                         [(4, 2, -1), (4, 2, 0), (4, 2, 1), (4, 3, -2), (4, 3, 0), (4, 3, 2)])

    def test_black_pawn_moves(self):
        self.assertEqual(sorted(self.game.get_legal_moves((4, 6, 0))),
                         [(4, 4, -2), (4, 4, 0), (4, 4, 2), (4, 5, -1), (4, 5, 0), (4, 5, 1)])

    def test_pawn_cannot_enter_or_pass_a_rock(self):
        moves = self.game.get_legal_moves((2, 1, 0))
        self.assertNotIn((2, 2, -1), moves)  # rock
        self.assertNotIn((2, 3, -2), moves)  # behind the rock (and a rock itself)

    def test_black_cannot_move_first(self):
        with self.assertRaises(ValueError):
            self.game.make_move((4, 6, 0), (4, 4, 0))
        self.assertEqual(self.game.current_player, "white")

    def test_illegal_move_rejected(self):
        with self.assertRaises(ValueError):
            self.game.make_move((0, 0, 0), (0, 5, 0))
        with self.assertRaises(ValueError):
            self.game.make_move((3, 3, 0), (3, 4, 0))  # empty square
        with self.assertRaises(ValueError):
            self.game.make_move((2, 2, -1), (2, 3, -1))  # rock

    def test_turns_alternate(self):
        self.game.make_move((4, 1, 0), (4, 3, 0))
        self.assertEqual(self.game.current_player, "black")
        self.game.make_move((4, 6, 0), (4, 4, 0))
        self.assertEqual(self.game.current_player, "white")
        self.assertEqual(len(self.game.move_history), 2)


class TestKingCaptures(unittest.TestCase):
    """The king steps on its own layer or straight up and down. One step sideways together
    with one layer up or down it cannot step, but it can capture there."""

    def test_cannot_step_diagonally_between_layers(self):
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black")}, rocks=False)
        moves = game.get_legal_moves((3, 3, 0))
        self.assertEqual(len(moves), 10)
        for blocked in ((4, 3, 1), (2, 3, -1), (3, 4, 1), (3, 2, -1)):
            self.assertNotIn(blocked, moves)

    def test_takes_a_queen_that_checks_from_there(self):
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black"), (4, 3, 1): Queen("black")},
                           rocks=False)
        self.assertTrue(game.is_in_check("white"))
        self.assertIn((4, 3, 1), game.get_legal_moves((3, 3, 0)))
        game.make_move((3, 3, 0), (4, 3, 1))
        self.assertEqual(game.white_king_pos, (4, 3, 1))
        self.assertEqual(game.move_history[-1]['captured_piece'], "Queen(black)")
        game.undo_move()
        self.assertEqual(game.white_king_pos, (3, 3, 0))
        self.assertIsInstance(game.board.get_piece((4, 3, 1)), Queen)

    def test_cannot_take_a_protected_piece(self):
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black"), (4, 3, 1): Queen("black"),
                            (4, 7, 1): Rook("black")}, rocks=False)
        self.assertNotIn((4, 3, 1), game.get_legal_moves((3, 3, 0)))

    def test_takes_any_enemy_piece_there_but_not_its_own_or_a_rock(self):
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black"), (3, 4, 1): Knight("black"),
                            (2, 3, 1): Pawn("white")}, rocks=False)
        game.board.set_piece(Rock(), (3, 2, -1))
        moves = game.get_legal_moves((3, 3, 0))
        self.assertIn((3, 4, 1), moves)       # the knight does not attack the king, but can still be taken
        self.assertNotIn((2, 3, 1), moves)
        self.assertNotIn((3, 2, -1), moves)

    def test_three_axes_at_once_is_out_of_reach(self):
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black"), (4, 4, 1): Knight("black")},
                           rocks=False)
        self.assertNotIn((4, 4, 1), game.get_legal_moves((3, 3, 0)))

    def test_the_king_guards_those_squares(self):
        # The black king may not step next to the white king, diagonally between layers included
        game = custom_game({(3, 3, 0): King("white"), (5, 3, 1): King("black")}, current_player="black", rocks=False)
        self.assertNotIn((4, 3, 1), game.get_legal_moves((5, 3, 1)))
        self.assertIn((6, 3, 1), game.get_legal_moves((5, 3, 1)))
        # ... and a piece standing there is protected by its king
        game = custom_game({(3, 3, 0): King("white"), (7, 7, 2): King("black"), (4, 3, 1): Bishop("white"),
                            (4, 6, 1): Rook("black")}, current_player="black", rocks=False)
        game.make_move((4, 6, 1), (4, 3, 1))                 # rook takes the bishop
        self.assertIn((4, 3, 1), game.get_legal_moves((3, 3, 0)))   # and the king takes back

    def test_that_capture_can_be_the_only_way_out_of_mate(self):
        # Cornered in the Abyss by a queen one step sideways and one layer up. Without the
        # capture this would be checkmate.
        pieces = {(0, 0, -2): King("white"), (7, 7, 2): King("black"), (1, 0, -1): Queen("black"),
                  (0, 7, -2): Rook("black")}     # the rook covers the one square the queen does not
        game = custom_game(pieces, rocks=False)
        self.assertTrue(game.is_in_check("white"))
        self.assertEqual(game.get_legal_moves((0, 0, -2)), [(1, 0, -1)])
        self.assertFalse(game.is_checkmate("white"))
        protected = custom_game({**pieces, (1, 6, -1): Rook("black")}, rocks=False)
        self.assertTrue(protected.is_checkmate("white"))


class TestStartingArmy(unittest.TestCase):
    def test_extra_knights_below_bishops_above_and_pawns_at_the_edges(self):
        game = GameState()
        for color, rank in (("white", 0), ("black", 7)):
            for x in (1, 6):
                piece = game.board.get_piece((x, rank, -1))
                self.assertIsInstance(piece, Knight)
                self.assertEqual(piece.color, color)
            for x in (2, 5):
                piece = game.board.get_piece((x, rank, 1))
                self.assertIsInstance(piece, Bishop)
                self.assertEqual(piece.color, color)
            pawn_rank = 1 if color == "white" else 6
            for x in (1, 6):
                for z in (2, -2):
                    piece = game.board.get_piece((x, pawn_rank, z))
                    self.assertIsInstance(piece, Pawn)
                    self.assertEqual(piece.color, color)
                    self.assertFalse(piece.has_moved)
            self.assertEqual(len(game.get_all_pieces_of_color(color)), 24)

    def test_nothing_is_attacked_before_the_first_move(self):
        game = GameState()
        for color, enemy in (("white", "black"), ("black", "white")):
            for coord, piece in game.get_all_pieces_of_color(color):
                self.assertFalse(game.is_square_under_attack(coord, enemy), f"{piece} on {coord}")
        moves = [(coord, move) for coord, _ in game.get_all_pieces_of_color("white")
                 for move in game.get_legal_moves(coord)]
        self.assertEqual(len(moves), 157)
        self.assertTrue(all(game.board.get_piece(move) is None for _, move in moves))

    def test_the_new_pieces_can_move_at_once(self):
        game = GameState()
        self.assertEqual(len(game.get_legal_moves((1, 0, -1))), 7)    # a Dungeon knight
        self.assertEqual(len(game.get_legal_moves((2, 0, 1))), 10)    # a Sky bishop


class TestBlocking(unittest.TestCase):
    def test_rock_blocks_rook_and_cannot_be_captured(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (2, 0, -1): Rook("white")})
        moves = game.get_legal_moves((2, 0, -1))
        self.assertIn((2, 1, -1), moves)
        self.assertNotIn((2, 2, -1), moves)  # the rock
        self.assertNotIn((2, 3, -1), moves)  # behind the rock

    def test_knight_ignores_rocks_in_the_way_but_cannot_land_on_one(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (4, 2, -1): Knight("white")})
        moves = game.get_legal_moves((4, 2, -1))
        self.assertIn((4, 4, -2), moves)     # past the rocks at (4,3,-1) and (4,3,-2)
        self.assertNotIn((3, 4, -1), moves)  # a rock
        self.assertIn((2, 3, -1), moves)     # past the rock at (3,3,-1)

    def test_pawn_double_step_blocked(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 1, 0): Pawn("white"), (0, 2, 0): Knight("black")})
        moves = game.get_legal_moves((0, 1, 0))
        self.assertNotIn((0, 2, 0), moves)
        self.assertNotIn((0, 3, 0), moves)
        self.assertIn((0, 3, 2), moves)  # climbing path is still open

    def test_pinned_piece_cannot_move_away(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (4, 1, 0): Rook("white"), (4, 6, 0): Rook("black")})
        moves = game.get_legal_moves((4, 1, 0))
        self.assertTrue(moves)
        self.assertTrue(all(x == 4 and z == 0 for x, _, z in moves))


class TestCheck(unittest.TestCase):
    def test_check_from_another_layer(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (4, 0, 2): Rook("black")})
        self.assertTrue(game.is_in_check("white"))
        self.assertFalse(game.is_checkmate("white"))

    def test_must_get_out_of_check(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (4, 0, 2): Rook("black"), (0, 1, 0): Pawn("white")})
        self.assertEqual(game.get_legal_moves((0, 1, 0)), [])

    def test_checkmate(self):
        game = custom_game({(0, 0, -2): King("white"), (2, 2, -2): King("black"),
                            (1, 1, -2): Queen("black"), (0, 5, -1): Rook("black")}, rocks=False)
        self.assertTrue(game.is_checkmate("white"))
        self.assertFalse(game.is_stalemate("white"))

    def test_stalemate(self):
        game = custom_game({(0, 0, -2): King("white"), (7, 7, 2): King("black"),
                            (1, 2, -2): Queen("black"), (5, 0, -1): Rook("black")}, rocks=False)
        self.assertFalse(game.is_in_check("white"))
        self.assertTrue(game.is_stalemate("white"))
        self.assertTrue(game.is_draw())


class TestCastling(unittest.TestCase):
    def setUp(self):
        self.game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                 (0, 0, 0): Rook("white"), (7, 0, 0): Rook("white")})

    def test_both_sides_available(self):
        moves = self.game.get_legal_moves((4, 0, 0))
        self.assertIn((6, 0, 0), moves)
        self.assertIn((2, 0, 0), moves)

    def test_kingside_castle_and_undo(self):
        before = snapshot(self.game)
        self.game.make_move((4, 0, 0), (6, 0, 0))
        self.assertIsInstance(self.game.board.get_piece((6, 0, 0)), King)
        self.assertIsInstance(self.game.board.get_piece((5, 0, 0)), Rook)
        self.assertEqual(self.game.white_king_pos, (6, 0, 0))
        self.assertEqual(self.game.move_history[-1]['special_move'], "castling")
        self.assertTrue(self.game.undo_move())
        self.assertEqual(snapshot(self.game), before)

    def test_queenside_castle(self):
        self.game.make_move((4, 0, 0), (2, 0, 0))
        self.assertIsInstance(self.game.board.get_piece((3, 0, 0)), Rook)
        self.assertIsNone(self.game.board.get_piece((0, 0, 0)))

    def test_no_castle_through_attacked_square(self):
        self.game.board.set_piece(Rook("black"), (5, 5, 0))
        moves = self.game.get_legal_moves((4, 0, 0))
        self.assertNotIn((6, 0, 0), moves)
        self.assertIn((2, 0, 0), moves)

    def test_no_castle_after_king_moved(self):
        self.game.make_move((4, 0, 0), (4, 1, 0))
        self.game.make_move((4, 7, 0), (4, 6, 0))
        self.game.make_move((4, 1, 0), (4, 0, 0))
        self.game.make_move((4, 6, 0), (4, 7, 0))
        self.assertNotIn((6, 0, 0), self.game.get_legal_moves((4, 0, 0)))


class TestEnPassant(unittest.TestCase):
    def setUp(self):
        self.game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                 (4, 4, 0): moved(Pawn("white")), (0, 4, 0): moved(Pawn("white")),
                                 (3, 6, 0): Pawn("black")}, current_player="black")

    def test_planar_en_passant_and_undo(self):
        self.game.make_move((3, 6, 0), (3, 4, 0))
        self.assertIn((3, 5, 0), self.game.get_legal_moves((4, 4, 0)))
        self.assertNotIn((3, 5, 0), self.game.get_legal_moves((0, 4, 0)))  # only the adjacent pawn
        before = snapshot(self.game)
        self.game.make_move((4, 4, 0), (3, 5, 0))
        self.assertIsNone(self.game.board.get_piece((3, 4, 0)))
        self.assertEqual(self.game.move_history[-1]['special_move'], "en_passant")
        self.assertTrue(self.game.undo_move())
        self.assertEqual(snapshot(self.game), before)

    def test_climbing_double_step_en_passant(self):
        self.game.make_move((3, 6, 0), (3, 4, 2))
        self.assertIn((3, 5, 1), self.game.get_legal_moves((4, 4, 0)))
        self.game.make_move((4, 4, 0), (3, 5, 1))
        self.assertIsNone(self.game.board.get_piece((3, 4, 2)))

    def test_en_passant_expires(self):
        self.game.make_move((3, 6, 0), (3, 4, 0))
        self.game.make_move((4, 0, 0), (4, 1, 0))
        self.game.make_move((4, 7, 0), (4, 6, 0))
        self.assertNotIn((3, 5, 0), self.game.get_legal_moves((4, 4, 0)))

    def test_single_step_is_not_en_passant(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (4, 4, 0): moved(Pawn("white")), (3, 5, 0): moved(Pawn("black"))},
                           current_player="black")
        game.make_move((3, 5, 0), (3, 4, 0))
        self.assertNotIn((3, 5, 0), game.get_legal_moves((4, 4, 0)))


class TestPromotion(unittest.TestCase):
    def setUp(self):
        self.game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                 (0, 6, 1): moved(Pawn("white"))})

    def test_promotion_flow(self):
        self.game.make_move((0, 6, 1), (0, 7, 1))
        self.assertEqual(self.game.pending_promotion, (0, 7, 1))
        self.assertEqual(self.game.current_player, "white")  # turn not passed yet
        with self.assertRaises(ValueError):
            self.game.make_move((4, 0, 0), (4, 1, 0))
        with self.assertRaises(ValueError):
            self.game.promote_pawn((0, 7, 1), King("white"))
        with self.assertRaises(ValueError):
            self.game.promote_pawn((0, 7, 1), Queen("black"))
        self.game.promote_pawn((0, 7, 1), Queen("white"))
        self.assertIsInstance(self.game.board.get_piece((0, 7, 1)), Queen)
        self.assertIsNone(self.game.pending_promotion)
        self.assertEqual(self.game.current_player, "black")

    def test_undo_promotion_takes_back_the_whole_turn(self):
        before = snapshot(self.game)
        self.game.make_move((0, 6, 1), (0, 7, 1))
        self.game.promote_pawn((0, 7, 1), Knight("white"))
        self.assertTrue(self.game.undo_move())
        self.assertEqual(snapshot(self.game), before)

    def test_undo_while_promotion_pending(self):
        before = snapshot(self.game)
        self.game.make_move((0, 6, 1), (0, 7, 1))
        self.assertTrue(self.game.undo_move())
        self.assertEqual(snapshot(self.game), before)

    def test_cannot_promote_without_pending_pawn(self):
        with self.assertRaises(ValueError):
            self.game.promote_pawn((0, 6, 1), Queen("white"))


class TestUndo(unittest.TestCase):
    def test_nothing_to_undo(self):
        self.assertFalse(GameState().undo_move())

    def test_undo_restores_capture_and_has_moved(self):
        game = GameState()
        start = snapshot(game)
        game.make_move((4, 1, 0), (4, 3, 0))
        game.make_move((3, 6, 0), (3, 4, 0))
        after_two = snapshot(game)
        game.make_move((4, 3, 0), (3, 4, 0))  # capture
        self.assertEqual(game.move_history[-1]['captured_piece'], "Pawn(black)")
        self.assertTrue(game.undo_move())
        self.assertEqual(snapshot(game), after_two)
        game.undo_move()
        game.undo_move()
        self.assertEqual(snapshot(game), start)
        # Other pawns were never touched by the undone moves
        self.assertIn((0, 3, 0), game.get_legal_moves((0, 1, 0)))


class TestDraw(unittest.TestCase):
    def test_bare_kings(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black")})
        self.assertTrue(game.is_insufficient_material())

    def test_bishop_plus_queen_is_enough(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (2, 0, 0): Bishop("white"), (3, 0, 0): Queen("white")})
        self.assertFalse(game.is_insufficient_material())

    def test_insufficient_material_is_judged_for_each_player(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 0, 0): Queen("white"), (1, 7, 0): Knight("black")})
        self.assertFalse(game.has_insufficient_material("white"))
        self.assertTrue(game.has_insufficient_material("black"))
        self.assertFalse(game.is_insufficient_material())

    def test_a_lone_rook_cannot_mate_where_the_king_can_change_layer(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"), (0, 0, 0): Rook("white")})
        self.assertTrue(game.has_insufficient_material("white"))
        self.assertEqual(game.get_draw_reason(), "insufficient_material")
        two_rooks = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                                 (0, 0, 0): Rook("white"), (7, 0, 0): Rook("white")})
        self.assertFalse(two_rooks.has_insufficient_material("white"))

    def test_a_lone_rook_is_enough_on_a_flat_board(self):
        game = GameState(size=5, z_min=0, z_max=0)
        for coord, piece in {(0, 4, 0): King("black"), (0, 2, 0): King("white"), (4, 3, 0): Rook("white")}.items():
            game.board.set_piece(piece, coord)
        game.reset_tracking()
        self.assertFalse(game.has_insufficient_material("white"))
        self.assertIsNone(game.get_draw_reason())
        game.make_move((4, 3, 0), (4, 4, 0))
        self.assertTrue(game.is_checkmate("black"))

    def test_bishops_on_one_square_color_cannot_mate(self):
        same = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 0, 0): Bishop("white"), (1, 1, 0): Bishop("white")})
        self.assertTrue(same.has_insufficient_material("white"))
        mixed = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                             (0, 0, 0): Bishop("white"), (1, 0, 0): Bishop("white")})
        self.assertFalse(mixed.has_insufficient_material("white"))

    def test_a_bishops_square_color_depends_on_its_layer(self):
        # One step sideways and one layer up is a bishop move, so those two squares share a color
        same = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 0, 0): Bishop("white"), (1, 0, 1): Bishop("white")})
        self.assertIn((1, 0, 1), Bishop("white").get_possible_moves((0, 0, 0)))
        self.assertTrue(same.has_insufficient_material("white"))
        # The square straight above is the other color
        mixed = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                             (0, 0, 0): Bishop("white"), (0, 0, 1): Bishop("white")})
        self.assertFalse(mixed.has_insufficient_material("white"))

    def test_a_bishop_never_leaves_its_square_color(self):
        bishop = Bishop("white")
        for start in ((0, 0, 0), (3, 4, -2), (7, 2, 1)):
            for target in bishop.get_possible_moves(start):
                self.assertEqual(bishop.get_square_color(target), bishop.get_square_color(start))

    def test_no_draw_while_a_pawn_waits_for_promotion(self):
        # White's king is walled in by rocks, so until the pawn is promoted White has no move at all
        pieces = {(0, 0, -2): King("white"), (7, 7, 2): King("black"), (5, 6, 0): moved(Pawn("white"))}
        for coord in King("white").get_possible_moves((0, 0, -2)):
            pieces[coord] = Rock()
        game = custom_game(pieces, rocks=False)
        self.assertEqual(game.get_legal_moves((0, 0, -2)), [])
        game.make_move((5, 6, 0), (5, 7, 0))
        self.assertEqual(game.pending_promotion, (5, 7, 0))
        self.assertTrue(game.is_stalemate("white"))  # true of the half-finished turn, but not a result
        self.assertIsNone(game.get_draw_reason())
        game.promote_pawn((5, 7, 0), Queen("white"))
        self.assertIsNone(game.get_draw_reason())

    def test_no_draw_rules_without_both_kings(self):
        # A practice board: one knight and nothing else is not "insufficient material"
        game = GameState()
        game.board.board = {}
        game.board.set_piece(Knight("white"), (3, 3, 0))
        game.reset_tracking()
        self.assertIsNone(game.get_draw_reason())
        game.make_move((3, 3, 0), (4, 5, 0))  # black, with no pieces, is not "stalemated" either
        self.assertIsNone(game.get_draw_reason())


class TestAmbiguousOrigins(unittest.TestCase):
    """Which other pieces could have made the same move (move notation needs to tell them apart)"""

    def test_usually_nobody_else_could_make_the_move(self):
        game = GameState()
        self.assertEqual(game.get_ambiguous_origins((1, 0, 0), (2, 2, 0)), [])
        self.assertEqual(game.get_ambiguous_origins((4, 1, 0), (4, 3, 0)), [])
        self.assertEqual(game.get_ambiguous_origins((3, 3, 0), (3, 4, 0)), [])  # empty square

    def test_two_knights_reaching_one_square(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 1, 0): Knight("white"), (4, 1, 0): Knight("white")}, rocks=False)
        self.assertEqual(game.get_ambiguous_origins((0, 1, 0), (2, 2, 0)), [(4, 1, 0)])
        self.assertEqual(game.get_ambiguous_origins((4, 1, 0), (2, 2, 0)), [(0, 1, 0)])
        self.assertEqual(game.get_ambiguous_origins((0, 1, 0), (1, 3, 0)), [])

    def test_a_pinned_piece_does_not_count(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 1): King("black"),
                            (0, 1, 0): Knight("white"), (4, 1, 0): Knight("white"),
                            (4, 5, 0): Rook("black")}, rocks=False)
        self.assertEqual(game.get_legal_moves((4, 1, 0)), [])
        self.assertEqual(game.get_ambiguous_origins((0, 1, 0), (2, 2, 0)), [])

    def test_other_kinds_and_the_opponent_do_not_count(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (0, 3, 0): Rook("white"), (7, 3, 0): Queen("white"),
                            (3, 6, 0): Rook("black")}, rocks=False)
        self.assertEqual(game.get_ambiguous_origins((0, 3, 0), (3, 3, 0)), [])

    def test_pawns_on_different_layers_stepping_to_one_square(self):
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): King("black"),
                            (2, 3, 0): moved(Pawn("white")), (2, 3, 1): moved(Pawn("white")),
                            (2, 3, -1): moved(Pawn("white"))}, rocks=False)
        self.assertEqual(sorted(game.get_ambiguous_origins((2, 3, 0), (2, 4, 0))), [(2, 3, -1), (2, 3, 1)])
        # The Sky pawn cannot reach the Dungeon in one step
        self.assertEqual(game.get_ambiguous_origins((2, 3, -1), (2, 4, -1)), [(2, 3, 0)])


class TestSmallBoard(unittest.TestCase):
    def small(self, pieces, current_player="white"):
        game = GameState(size=5, z_min=-1, z_max=1)
        for coord, piece in pieces.items():
            game.board.set_piece(piece, coord)
        game.current_player = current_player
        game.reset_tracking()
        return game

    def test_small_board_starts_empty_with_its_own_bounds(self):
        game = GameState(size=5, z_min=-1, z_max=1)
        self.assertEqual(game.board.board, {})
        self.assertEqual(game.board.bounds, (5, -1, 1))
        self.assertIsNone(game.white_king_pos)
        with self.assertRaises(ValueError):
            game.board.get_piece((5, 0, 0))
        with self.assertRaises(ValueError):
            game.board.get_piece((0, 0, 2))

    def test_knight_in_the_centre_has_16_moves(self):
        game = self.small({(2, 2, 0): Knight("white")})
        moves = game.get_legal_moves((2, 2, 0))
        self.assertEqual(len(moves), 16)
        self.assertTrue(all(0 <= x < 5 and 0 <= y < 5 and -1 <= z <= 1 for x, y, z in moves))

    def test_rook_and_queen_stop_at_the_small_edges(self):
        game = self.small({(0, 0, 0): Rook("white"), (2, 2, 0): Queen("black")})
        self.assertEqual(len(game.get_legal_moves((0, 0, 0))), 4 + 4 + 2)  # rank, file, up and down
        game.current_player = "black"
        self.assertTrue(all(0 <= x < 5 and 0 <= y < 5 and -1 <= z <= 1
                            for x, y, z in game.get_legal_moves((2, 2, 0))))

    def test_pawn_promotes_on_the_last_rank_of_a_small_board(self):
        game = self.small({(0, 0, 0): King("white"), (4, 4, 1): King("black"),
                           (2, 3, 0): moved(Pawn("white")), (2, 1, 0): moved(Pawn("black"))})
        game.make_move((2, 3, 0), (2, 4, 0))
        self.assertEqual(game.pending_promotion, (2, 4, 0))
        game.promote_pawn((2, 4, 0), Queen("white"))
        game.make_move((2, 1, 0), (2, 0, 0))
        self.assertEqual(game.pending_promotion, (2, 0, 0))

    def test_checkmate_on_a_small_board(self):
        game = self.small({(0, 0, -1): King("white"), (2, 2, -1): King("black"),
                           (1, 1, -1): Queen("black"), (0, 3, 0): Rook("black")})
        self.assertTrue(game.is_checkmate("white"))


# Both knights go out and come back: after these 4 moves the position repeats
KNIGHT_DANCE = [((1, 0, 0), (2, 2, 0)), ((1, 7, 0), (2, 5, 0)),
                ((2, 2, 0), (1, 0, 0)), ((2, 5, 0), (1, 7, 0))]


class TestThreefoldRepetition(unittest.TestCase):
    def test_third_occurrence_is_a_draw(self):
        game = GameState()
        shuttle(game, KNIGHT_DANCE)  # starting position seen twice
        self.assertFalse(game.is_threefold_repetition())
        self.assertIsNone(game.get_draw_reason())
        shuttle(game, KNIGHT_DANCE)  # three times
        self.assertTrue(game.is_threefold_repetition())
        self.assertEqual(game.get_draw_reason(), "repetition")
        self.assertTrue(game.is_draw())

    def test_undo_takes_the_repetition_back(self):
        game = GameState()
        shuttle(game, KNIGHT_DANCE, times=2)
        game.undo_move()
        self.assertFalse(game.is_threefold_repetition())
        game.make_move(*KNIGHT_DANCE[-1])
        self.assertTrue(game.is_threefold_repetition())

    def test_same_squares_but_other_player_to_move_is_a_different_position(self):
        game = GameState()
        shuttle(game, KNIGHT_DANCE[:2])
        shuttle(game, KNIGHT_DANCE[2:] + KNIGHT_DANCE[:2], times=2)
        # Knights-out position: reached 3 times, always with white to move
        self.assertTrue(game.is_threefold_repetition())
        game.make_move((6, 0, 0), (5, 2, 0))
        self.assertFalse(game.is_threefold_repetition())

    def test_lost_castling_rights_make_a_different_position(self):
        rook_dance = [((7, 0, 0), (7, 1, 0)), ((4, 7, 0), (4, 6, 0)),
                      ((7, 1, 0), (7, 0, 0)), ((4, 6, 0), (4, 7, 0))]
        game = custom_game({(4, 0, 0): King("white"), (4, 7, 0): moved(King("black")),
                            (7, 0, 0): Rook("white"), (0, 7, 1): Queen("black")})
        self.assertIn((6, 0, 0), game.get_legal_moves((4, 0, 0)))
        # The first position allowed castling; the rook has moved in every later one
        shuttle(game, rook_dance, times=2)
        self.assertFalse(game.is_threefold_repetition())
        shuttle(game, rook_dance)
        self.assertTrue(game.is_threefold_repetition())

    def test_en_passant_option_makes_a_different_position(self):
        game = custom_game({(4, 0, 0): moved(King("white")), (4, 7, 0): moved(King("black")),
                            (4, 4, 0): moved(Pawn("white")), (3, 6, 0): Pawn("black"),
                            (0, 0, 2): Knight("white"), (0, 7, 2): Knight("black")},
                           current_player="black")
        game.make_move((3, 6, 0), (3, 4, 0))  # en passant is possible now, and only now
        knight_dance = [((0, 0, 2), (1, 2, 2)), ((0, 7, 2), (1, 5, 2)),
                        ((1, 2, 2), (0, 0, 2)), ((1, 5, 2), (0, 7, 2))]
        shuttle(game, knight_dance, times=2)
        self.assertFalse(game.is_threefold_repetition())
        shuttle(game, knight_dance)
        self.assertTrue(game.is_threefold_repetition())


class TestMoveLimit(unittest.TestCase):
    def test_clock_counts_quiet_moves_and_restarts(self):
        game = GameState()
        shuttle(game, KNIGHT_DANCE[:2])
        self.assertEqual(game.halfmove_clock, 2)
        game.make_move((4, 1, 0), (4, 3, 0))  # pawn move
        self.assertEqual(game.halfmove_clock, 0)
        game.make_move((3, 6, 0), (3, 4, 0))
        game.make_move((2, 2, 0), (3, 4, 0))  # knight takes pawn
        self.assertEqual(game.halfmove_clock, 0)
        game.make_move((2, 5, 0), (1, 7, 0))
        self.assertEqual(game.halfmove_clock, 1)
        game.undo_move()
        game.undo_move()
        game.undo_move()
        game.undo_move()
        self.assertEqual(game.halfmove_clock, 2)

    def test_draw_when_limit_reached(self):
        game = custom_game({(4, 0, 0): moved(King("white")), (4, 7, 0): moved(King("black")),
                            (1, 0, 0): Queen("white")})
        game.move_limit = 3
        # Walk both kings sideways so no position repeats
        for x in (5, 6):
            game.make_move((x - 1, 0, 0), (x, 0, 0))
            game.make_move((x - 1, 7, 0), (x, 7, 0))
        self.assertIsNone(game.get_draw_reason())
        game.make_move((6, 0, 0), (7, 0, 0))
        game.make_move((6, 7, 0), (7, 7, 0))
        self.assertEqual(game.halfmove_clock, 6)
        self.assertTrue(game.is_move_limit_reached())
        self.assertEqual(game.get_draw_reason(), "move_limit")
        game.undo_move()
        self.assertFalse(game.is_draw())

    def test_default_limit_is_fifty_moves_each(self):
        game = GameState()
        self.assertEqual(game.move_limit, 50)
        game.halfmove_clock = 99
        self.assertFalse(game.is_move_limit_reached())
        game.halfmove_clock = 100
        self.assertTrue(game.is_move_limit_reached())

    def test_checkmate_beats_a_draw(self):
        game = custom_game({(0, 0, -2): King("white"), (2, 2, -2): King("black"),
                            (1, 1, -2): Queen("black"), (0, 5, -1): Rook("black")}, rocks=False)
        game.halfmove_clock = 100
        self.assertTrue(game.is_checkmate("white"))
        self.assertIsNone(game.get_draw_reason())
        self.assertFalse(game.is_draw())


if __name__ == '__main__':
    unittest.main()
