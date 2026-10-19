"""
Team games: two players a side share the army and take turns with it. White's first player
moves, then Black's first, then White's second and Black's second.
"""
import unittest

from tests.test_online import OnlineTestCase, Player

E2E4, E7E5, D2D4, D7D5, G1F3 = (([4, 1, 0], [4, 3, 0]), ([4, 6, 0], [4, 4, 0]), ([3, 1, 0], [3, 3, 0]),
                                ([3, 6, 0], [3, 4, 0]), ([6, 0, 0], [5, 2, 0]))


class TestTeams(OnlineTestCase):
    def four_players(self):
        """A 2v2 online game, everyone seated. Returns (white, white2, black, black2)."""
        data = self.open(kind="online", side="white", teams=True).get_json()
        white = Player(data["game_id"], data["seat"])
        seated = {"white": white}
        for side in ("black", "white", "black"):
            player = Player(data["game_id"])
            joined = player.post('/api/game/join', {"side": side}).get_json()
            player.seat = joined["seat"]
            seated[joined["online"]["seat"]] = player
        return seated["white"], seated["white2"], seated["black"], seated["black2"]

    def test_four_seats_filled_by_the_side_asked_for(self):
        white, white2, black, black2 = self.four_players()
        state = white2.state()
        self.assertEqual(state["online"]["seat"], "white2")
        self.assertEqual(state["online"]["you"], "white")
        self.assertEqual(state["online"]["seats"], {"white": True, "black": True, "white2": True, "black2": True})
        self.assertEqual(state["teams"], {"turn": "white"})
        late = Player(white.game_id)
        joined = late.post('/api/game/join', {"side": "black"}).get_json()
        self.assertEqual((joined["seat"], joined["online"]["you"]), (None, None))   # watching

    def test_teammates_take_turns(self):
        white, white2, black, black2 = self.four_players()
        self.assertEqual(white2.move(*E2E4).get_json()["error"], "It is your teammate's move")
        self.assertTrue(white.move(*E2E4).get_json()["success"])
        self.assertEqual(black2.move(*E7E5).get_json()["error"], "It is your teammate's move")
        self.assertEqual(black.move(*E7E5).get_json()["teams"], {"turn": "white2"})
        self.assertEqual(white.move(*D2D4).get_json()["error"], "It is your teammate's move")
        self.assertTrue(white2.move(*D2D4).get_json()["success"])
        self.assertEqual(black2.move(*D7D5).get_json()["teams"], {"turn": "white"})
        self.assertTrue(white.move(*G1F3).get_json()["success"])

    def test_a_take_back_hands_the_turn_back(self):
        white, white2, black, black2 = self.four_players()
        white.move(*E2E4)
        black.move(*E7E5)
        white2.move(*D2D4)
        self.assertTrue(white2.post('/api/game/offer', {"kind": "takeback"}).get_json()["success"])
        answer = black2.post('/api/game/answer', {"accept": True}).get_json()   # either opponent may answer
        self.assertEqual((len(answer["move_history"]), answer["teams"]), (2, {"turn": "white2"}))

    def test_without_a_side_the_seats_alternate_colors(self):
        data = self.open(kind="online", side="black", teams=True).get_json()
        seats = [Player(data["game_id"]).post('/api/game/join').get_json()["online"]["seat"] for _ in range(3)]
        self.assertEqual(seats, ["white", "white2", "black2"])

    def test_a_team_against_the_computer_online(self):
        data = self.open(kind="online", side="white", teams=True,
                         computer={"color": "black", "level": "easy"}).get_json()
        self.assertEqual(data["online"]["seats"], {"white": True, "white2": False})
        white = Player(data["game_id"], data["seat"])
        white2 = Player(data["game_id"])
        white2.seat = white2.post('/api/game/join', {"side": "black"}).get_json()["seat"]
        self.assertIsNone(white2.seat)   # the computer's side has no seats
        white2.seat = white2.post('/api/game/join').get_json()["seat"]
        self.assertTrue(white.move(*E2E4).get_json()["success"])
        reply = white2.post('/api/game/computer-move').get_json()
        self.assertTrue(reply["success"], reply.get("error"))
        self.assertEqual(reply["teams"], {"turn": "white2"})
        self.assertTrue(white2.move(*D2D4).get_json()["success"])
        # A take-back needs nobody's leave: it undoes the computer's reply too
        taken = white2.post('/api/game/offer', {"kind": "takeback"}).get_json()
        self.assertEqual((len(taken["move_history"]), taken["online"]["offer"]), (2, None))
        self.assertEqual(taken["teams"], {"turn": "white2"})

    def test_team_games_on_one_screen_say_whose_turn_it_is(self):
        data = self.open(kind="computer", teams=True, computer={"color": "black", "level": "easy"}).get_json()
        self.assertEqual(data["teams"], {"turn": "white"})
        player = Player(data["game_id"])
        player.move(*E2E4)
        self.assertEqual(player.post('/api/game/computer-move').get_json()["teams"], {"turn": "white2"})
        self.assertIsNone(self.open(kind="local").get_json()["teams"])

    def test_only_teams_play_the_computer_online(self):
        refused = self.open(kind="online", computer={"color": "black", "level": "easy"})
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(self.open(kind="online", side="black", teams=True,
                                   computer={"color": "black", "level": "easy"}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
