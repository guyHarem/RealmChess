"""
Rooms and online play: every game has its own address, and in an online game each player
holds a secret key for one color.
"""
import unittest

from api import rooms as rooms_module
from api.app import app, rooms


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def tick(self, seconds):
        self.now += seconds


class Player:
    """One browser: remembers its key and sends it with every request"""
    def __init__(self, game_id, seat=None):
        self.client = app.test_client()
        self.game_id = game_id
        self.seat = seat

    def call(self, method, path, body=None, **query):
        headers = {"X-Seat": self.seat} if self.seat else {}
        return self.client.open(path, method=method, json=body, headers=headers,
                                query_string={"game": self.game_id, **query})

    def get(self, path, **query):
        return self.call("GET", path, **query)

    def post(self, path, body=None):
        return self.call("POST", path, body or {})

    def state(self):
        return self.get('/api/game/state').get_json()

    def move(self, from_coord, to_coord):
        return self.post('/api/game/move', {"from": from_coord, "to": to_coord})


class OnlineTestCase(unittest.TestCase):
    def setUp(self):
        self.time = FakeTime()
        rooms._now = self.time

    def tearDown(self):
        import time
        rooms._now = time.monotonic
        for room_id in [room_id for room_id in rooms._rooms if room_id not in ("main", "practice")]:
            del rooms._rooms[room_id]

    def open(self, **body):
        return app.test_client().post('/api/games', json=body)

    def two_players(self, side="white", **options):
        """An online game with both seats taken. Returns (white, black)."""
        data = self.open(kind="online", side=side, **options).get_json()
        creator = Player(data["game_id"], data["seat"])
        friend = Player(data["game_id"])
        friend.seat = friend.post('/api/game/join').get_json()["seat"]
        return (creator, friend) if side == "white" else (friend, creator)


class TestRooms(OnlineTestCase):
    def test_every_new_game_gets_its_own_room(self):
        first = self.open(kind="local").get_json()
        second = self.open(kind="local").get_json()
        self.assertNotEqual(first["game_id"], second["game_id"])
        self.assertEqual((first["kind"], first["online"], first["status"]), ("local", None, "ongoing"))
        self.assertNotIn("seat", first)

        one, two = Player(first["game_id"]), Player(second["game_id"])
        self.assertEqual(one.move([4, 1, 0], [4, 3, 0]).status_code, 200)
        self.assertEqual(len(one.state()["move_history"]), 1)
        self.assertEqual(len(two.state()["move_history"]), 0)
        self.assertEqual(len(app.test_client().get('/api/game/state').get_json()["move_history"]), 0)

    def test_options_reach_the_new_game(self):
        data = self.open(kind="local", rocks=False, move_limit=30, clock={"initial": 60, "increment": 2}).get_json()
        self.assertEqual((len(data["board"]), data["move_limit"], data["clock"]["initial"]), (48, 30, 60))

    def test_computer_game(self):
        data = self.open(kind="computer", computer={"color": "black", "level": "easy"}).get_json()
        self.assertEqual((data["kind"], data["computer"]), ("computer", {"color": "black", "level": "easy"}))
        player = Player(data["game_id"])
        player.move([4, 1, 0], [4, 3, 0])
        reply = player.post('/api/game/computer-move').get_json()
        self.assertTrue(reply["success"], reply.get("error"))
        self.assertEqual(len(reply["move_history"]), 2)

    def test_practice_rooms_are_separate_scratch_boards(self):
        one = Player(self.open(kind="practice").get_json()["game_id"])
        two = Player(self.open(kind="practice").get_json()["game_id"])
        setup = {"size": 5, "z_min": -1, "z_max": 1, "pieces": [{"coord": [2, 2, 0], "type": "Knight", "color": "white"}]}
        self.assertEqual(one.post('/api/debug/setup', setup).status_code, 200)
        self.assertEqual(one.state()["board_size"]["size"], 5)
        self.assertEqual(two.state()["board_size"]["size"], 8)

    def test_bad_requests(self):
        self.assertEqual(self.open(kind="tournament").status_code, 400)
        self.assertEqual(self.open(kind="online", side="green").status_code, 400)
        self.assertEqual(self.open(kind="local", computer={"color": "black", "level": "easy"}).status_code, 400)
        self.assertEqual(self.open(kind="computer").status_code, 400)
        self.assertEqual(self.open(kind="local", move_limit=0).status_code, 400)

    def test_a_room_that_is_gone(self):
        res = Player("nosuchroom").get('/api/game/state')
        self.assertEqual((res.status_code, res.get_json()["gone"]), (404, True))

    def test_idle_rooms_are_removed_after_a_day(self):
        old = self.open(kind="local").get_json()["game_id"]
        self.time.tick(23 * 3600)
        Player(old).state()                       # still in use
        forgotten = self.open(kind="local").get_json()["game_id"]
        self.time.tick(2 * 3600)                  # 25 hours after it was opened, but used 2 hours ago
        self.assertEqual(Player(old).get('/api/game/state').status_code, 200)
        self.time.tick(25 * 3600)
        self.open(kind="local")                   # opening a room sweeps out the stale ones
        self.assertEqual(Player(old).get('/api/game/state').status_code, 404)
        self.assertEqual(Player(forgotten).get('/api/game/state').status_code, 404)
        self.assertEqual(app.test_client().get('/api/game/state').status_code, 200)   # "main" stays

    def test_the_server_can_be_full(self):
        limit = rooms_module.MAX_ROOMS
        rooms_module.MAX_ROOMS = len(rooms) + 1
        try:
            self.assertEqual(self.open(kind="local").status_code, 200)
            res = self.open(kind="local")
            self.assertEqual((res.status_code, res.get_json()["error"]), (400, "The server is full. Try again later."))
        finally:
            rooms_module.MAX_ROOMS = limit


class TestSeats(OnlineTestCase):
    def test_creator_sits_first_and_the_link_gives_the_other_seat(self):
        data = self.open(kind="online", side="black").get_json()
        self.assertEqual(data["kind"], "online")
        self.assertEqual(data["online"]["you"], "black")
        self.assertEqual(data["online"]["seats"], {"white": False, "black": True})
        self.assertTrue(data["seat"])

        friend = Player(data["game_id"])
        joined = friend.post('/api/game/join').get_json()
        self.assertEqual(joined["online"]["you"], "white")
        self.assertEqual(joined["online"]["seats"], {"white": True, "black": True})
        self.assertNotEqual(joined["seat"], data["seat"])

    def test_coming_back_gives_the_same_seat(self):
        white, black = self.two_players()
        again = black.post('/api/game/join').get_json()
        self.assertEqual((again["seat"], again["online"]["you"]), (black.seat, "black"))
        self.assertEqual(black.state()["online"]["you"], "black")

    def test_a_third_visitor_only_watches(self):
        white, black = self.two_players()
        watcher = Player(white.game_id)
        joined = watcher.post('/api/game/join').get_json()
        self.assertEqual((joined["seat"], joined["online"]["you"]), (None, None))
        self.assertEqual(joined["board"]["[4, 0, 0]"], "King(white)")
        res = watcher.move([4, 1, 0], [4, 3, 0])
        self.assertEqual((res.status_code, res.get_json()["error"]), (403, "You are watching this game"))
        self.assertEqual(watcher.post('/api/game/resign').status_code, 403)
        self.assertEqual(watcher.post('/api/game/offer', {"kind": "draw"}).status_code, 400)

    def test_only_the_player_to_move_can_move(self):
        white, black = self.two_players()
        res = black.move([4, 6, 0], [4, 4, 0])
        self.assertEqual((res.status_code, res.get_json()["error"]), (403, "It is not your move"))
        # Black cannot move White's pieces either, even on White's turn
        self.assertEqual(black.move([4, 1, 0], [4, 3, 0]).status_code, 403)
        self.assertEqual(white.move([4, 1, 0], [4, 3, 0]).status_code, 200)
        self.assertEqual(white.move([3, 1, 0], [3, 3, 0]).status_code, 403)
        self.assertEqual(black.move([4, 6, 0], [4, 4, 0]).status_code, 200)
        self.assertEqual(len(white.state()["move_history"]), 2)

    def test_a_made_up_key_is_a_watcher(self):
        white, black = self.two_players()
        intruder = Player(white.game_id, seat="not-a-real-key")
        self.assertIsNone(intruder.state()["online"]["you"])
        self.assertEqual(intruder.move([4, 1, 0], [4, 3, 0]).status_code, 403)

    def test_resigning_is_for_your_own_color(self):
        white, black = self.two_players()
        data = black.post('/api/game/resign', {"color": "white"}).get_json()   # the body is ignored
        self.assertEqual((data["status"], data["winner"]), ("resigned", "white"))

    def test_what_online_games_do_not_allow(self):
        white, black = self.two_players()
        for path in ('/api/game/undo', '/api/game/draw', '/api/game/new', '/api/debug/setup', '/api/debug/turn'):
            res = white.post(path)
            self.assertEqual((res.status_code, res.get_json()["error"]),
                             (400, "That is not available in an online game"), path)
        local = Player(self.open(kind="local").get_json()["game_id"])
        self.assertEqual(local.post('/api/game/join').status_code, 400)
        self.assertEqual(local.post('/api/game/offer', {"kind": "draw"}).status_code, 400)

    def test_promotion_is_the_movers_choice(self):
        white, black = self.two_players()
        room = rooms.get(white.game_id)
        from engine.pieces import King, Pawn, Queen
        pawn = Pawn("white")
        pawn.has_moved = True
        room.manager.game.board.board = {(0, 0, 0): King("white"), (7, 7, 2): King("black"),
                                         (3, 6, 0): pawn, (0, 1, 0): Queen("white")}
        room.manager.game.reset_tracking()
        self.assertEqual(white.move([3, 6, 0], [3, 7, 0]).get_json()["pending_promotion"], [3, 7, 0])
        promote = {"coord": [3, 7, 0], "piece_type": "Rook"}
        self.assertEqual(black.post('/api/game/promote', promote).status_code, 403)
        data = white.post('/api/game/promote', promote).get_json()
        self.assertEqual((data["board"]["[3, 7, 0]"], data["current_player"]), ("Rook(white)", "black"))


class TestKeepingUp(OnlineTestCase):
    def test_asking_again_gets_a_short_answer_until_something_changes(self):
        white, black = self.two_players()
        stamp = black.state()["stamp"]
        short = black.get('/api/game/state', since=stamp).get_json()
        self.assertEqual((short["unchanged"], short["stamp"]), (True, stamp))
        self.assertNotIn("board", short)
        self.assertEqual(short["online"]["you"], "black")

        white.move([4, 1, 0], [4, 3, 0])
        full = black.get('/api/game/state', since=stamp).get_json()
        self.assertNotIn("unchanged", full)
        self.assertEqual(full["board"]["[4, 3, 0]"], "Pawn(white)")
        self.assertNotEqual(full["stamp"], stamp)

    def test_joining_and_offers_also_count_as_changes(self):
        data = self.open(kind="online").get_json()
        white = Player(data["game_id"], data["seat"])
        stamp = white.state()["stamp"]
        black = Player(data["game_id"])
        black.seat = black.post('/api/game/join').get_json()["seat"]
        after_join = white.get('/api/game/state', since=stamp).get_json()
        self.assertEqual(after_join["online"]["seats"]["black"], True)
        black.post('/api/game/offer', {"kind": "draw"})
        after_offer = white.get('/api/game/state', since=after_join["stamp"]).get_json()
        self.assertEqual(after_offer["online"]["offer"], {"kind": "draw", "by": "black"})

    def test_who_is_connected(self):
        white, black = self.two_players()
        self.assertEqual(white.state()["online"]["connected"], {"white": True, "black": True})
        self.time.tick(10)                     # Black's page has gone quiet
        self.assertEqual(white.state()["online"]["connected"], {"white": True, "black": False})
        black.state()
        self.assertEqual(white.state()["online"]["connected"], {"white": True, "black": True})

    def test_an_empty_seat_is_not_connected(self):
        data = self.open(kind="online").get_json()
        self.assertEqual(data["online"]["connected"], {"white": True, "black": False})

    def test_running_out_of_time_shows_up_without_a_move(self):
        from api.game_manager import GameManager
        white, black = self.two_players(clock={"initial": 30, "increment": 0})
        manager = rooms.get(white.game_id).manager
        manager._now = self.time
        manager.clock._now = self.time
        white.move([4, 1, 0], [4, 3, 0])
        stamp = white.state()["stamp"]
        self.time.tick(31)
        data = white.get('/api/game/state', since=stamp).get_json()
        self.assertEqual((data.get("status"), data.get("winner")), ("timeout", "white"))


class TestOffers(OnlineTestCase):
    def offer(self, player, kind):
        return player.post('/api/game/offer', {"kind": kind})

    def answer(self, player, accept):
        return player.post('/api/game/answer', {"accept": accept})

    def test_draw_offer_accepted(self):
        white, black = self.two_players()
        data = self.offer(white, "draw").get_json()
        self.assertEqual((data["success"], data["online"]["offer"], data["status"]),
                         (True, {"kind": "draw", "by": "white"}, "ongoing"))
        self.assertEqual(black.state()["online"]["offer"], {"kind": "draw", "by": "white"})
        data = self.answer(black, True).get_json()
        self.assertEqual((data["status"], data["winner"], data["online"]["offer"]), ("agreed_draw", None, None))
        self.assertEqual(white.state()["status"], "agreed_draw")

    def test_draw_offer_declined(self):
        white, black = self.two_players()
        self.offer(white, "draw")
        data = self.answer(black, False).get_json()
        self.assertEqual((data["status"], data["online"]["offer"]), ("ongoing", None))

    def test_you_cannot_accept_your_own_offer_but_you_can_withdraw_it(self):
        white, black = self.two_players()
        self.offer(white, "draw")
        res = self.answer(white, True)
        self.assertEqual((res.status_code, res.get_json()["error"]), (400, "Your opponent has to answer that"))
        self.assertEqual(self.answer(white, False).get_json()["online"]["offer"], None)
        self.assertEqual(self.answer(black, True).get_json()["error"], "There is no offer to answer")

    def test_offering_a_draw_back_accepts_it(self):
        white, black = self.two_players()
        self.offer(white, "draw")
        self.assertEqual(self.offer(black, "draw").get_json()["status"], "agreed_draw")

    def test_a_move_turns_the_offer_down(self):
        white, black = self.two_players()
        self.offer(black, "draw")
        data = white.move([4, 1, 0], [4, 3, 0]).get_json()
        self.assertIsNone(data["online"]["offer"])

    def test_take_back_of_the_move_just_made(self):
        white, black = self.two_players()
        white.move([4, 1, 0], [4, 3, 0])
        self.offer(white, "takeback")              # Black has not replied yet
        data = self.answer(black, True).get_json()
        self.assertEqual((data["current_player"], data["move_history"], data["online"]["offer"]), ("white", [], None))
        self.assertEqual(white.move([3, 1, 0], [3, 3, 0]).status_code, 200)

    def test_take_back_after_the_opponent_replied(self):
        white, black = self.two_players()
        white.move([4, 1, 0], [4, 3, 0])
        black.move([4, 6, 0], [4, 4, 0])
        white.move([6, 0, 0], [5, 2, 0])
        black.move([1, 7, 0], [2, 5, 0])
        self.offer(white, "takeback")              # White's knight move, and Black's reply with it
        data = self.answer(black, True).get_json()
        self.assertEqual((data["current_player"], len(data["move_history"])), ("white", 2))
        self.assertEqual(data["board"]["[6, 0, 0]"], "Knight(white)")

    def test_take_back_declined_changes_nothing(self):
        white, black = self.two_players()
        white.move([4, 1, 0], [4, 3, 0])
        self.offer(white, "takeback")
        data = self.answer(black, False).get_json()
        self.assertEqual((len(data["move_history"]), data["current_player"]), (1, "black"))

    def test_nothing_to_take_back(self):
        white, black = self.two_players()
        res = self.offer(white, "takeback")
        self.assertEqual((res.status_code, res.get_json()["error"]), (400, "You have no move to take back"))
        white.move([4, 1, 0], [4, 3, 0])
        self.assertEqual(self.offer(black, "takeback").get_json()["error"], "You have no move to take back")

    def test_take_back_puts_the_clock_back(self):
        white, black = self.two_players(clock={"initial": 100, "increment": 0})
        manager = rooms.get(white.game_id).manager
        manager._now = self.time
        manager.clock._now = self.time
        white.move([4, 1, 0], [4, 3, 0])
        self.time.tick(20)
        black.move([4, 6, 0], [4, 4, 0])           # Black has 80 left
        self.time.tick(5)
        self.offer(black, "takeback")
        data = self.answer(white, True).get_json()
        self.assertEqual((data["current_player"], data["clock"]["black"], data["clock"]["running"]), ("black", 80, "black"))

    def test_no_offers_once_the_game_is_over(self):
        white, black = self.two_players()
        white.post('/api/game/resign')
        res = self.offer(black, "draw")
        self.assertEqual((res.status_code, res.get_json()["error"]), (400, "The game is over"))

    def test_unknown_offer(self):
        white, black = self.two_players()
        self.assertEqual(self.offer(white, "pizza").status_code, 400)


if __name__ == '__main__':
    unittest.main()
