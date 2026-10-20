"""
Playing strangers: open games in the lobby, what players can say to each other, claiming a
game the other side has left. And the admin side: anonymous play counts and feedback.
"""
import json
import os
import unittest
import unittest.mock

from api import handoff
from api.app import app, inbox, rooms, stats
from api.rooms import ABANDON_SECONDS, LOBBY_SECONDS, PHRASES, Rooms
from api.stats import Inbox, Stats
from tests.test_online import OnlineTestCase, Player


class LobbyTestCase(OnlineTestCase):
    def open_game(self, **options):
        data = self.open(kind="online", public=True, **options).get_json()
        self.assertTrue(data["success"], data.get("error"))
        return Player(data["game_id"], data["seat"])

    def lobby(self):
        return app.test_client().get('/api/lobby').get_json()


class TestLobby(LobbyTestCase):
    def test_an_open_game_is_listed_until_someone_joins(self):
        creator = self.open_game(side="black", portals="classic", clock={"initial": 300, "increment": 0})
        friend_game = self.open(kind="online").get_json()["game_id"]   # not open: not listed
        games = {game["id"]: game for game in self.lobby()["games"]}
        self.assertNotIn(friend_game, games)
        listed = games[creator.game_id]
        self.assertEqual((listed["free"], listed["portals"], listed["dynamite"], listed["clock"]["initial"]),
                         (["white"], True, False, 300))
        stranger = Player(creator.game_id)
        stranger.seat = stranger.post('/api/game/join').get_json()["seat"]
        self.assertEqual(stranger.state()["online"]["you"], "white")
        self.assertNotIn(creator.game_id, [game["id"] for game in self.lobby()["games"]])

    def test_a_game_whose_creator_left_leaves_the_lobby(self):
        creator = self.open_game()
        self.time.tick(LOBBY_SECONDS + 1)
        self.assertNotIn(creator.game_id, [game["id"] for game in self.lobby()["games"]])
        creator.state()   # back again
        self.assertIn(creator.game_id, [game["id"] for game in self.lobby()["games"]])

    def test_open_team_games_show_their_free_sides(self):
        creator = self.open_game(teams=True)
        listed = next(game for game in self.lobby()["games"] if game["id"] == creator.game_id)
        self.assertEqual((listed["teams"], listed["free"], listed["players"]), (True, ["black", "white"], 1))

    def test_only_online_games_are_open(self):
        self.assertFalse(self.open(kind="local", public=True).get_json()["success"])


class TestTalking(LobbyTestCase):
    def test_friends_say_anything_to_each_other(self):
        white, black = self.two_players()
        said = white.post('/api/game/say', {"text": "hi there", "to": "all"}).get_json()
        self.assertTrue(said["success"], said.get("error"))
        self.assertEqual(black.state()["online"]["chat"][-1]["text"], "hi there")
        self.assertEqual(Player(white.game_id).state()["online"]["chat"], [])   # watchers see none

    def test_strangers_pick_phrases(self):
        creator = self.open_game()
        stranger = Player(creator.game_id)
        stranger.seat = stranger.post('/api/game/join').get_json()["seat"]
        refused = stranger.post('/api/game/say', {"text": "anything I like", "to": "all"}).get_json()
        self.assertEqual(refused["error"], "In an open game, pick one of the phrases")
        self.assertTrue(stranger.post('/api/game/say', {"text": "Good luck!", "to": "all"}).get_json()["success"])
        self.assertEqual(creator.state()["online"]["chat"][-1]["text"], "Good luck!")
        self.assertIn("Good game!", self.lobby()["phrases"])

    def test_team_messages_stay_in_the_team_and_messages_to_all_reach_everyone(self):
        data = self.open(kind="online", teams=True).get_json()
        white = Player(data["game_id"], data["seat"])
        others = {}
        for side in ("black", "white", "black"):
            player = Player(data["game_id"])
            joined = player.post('/api/game/join', {"side": side}).get_json()
            player.seat = joined["seat"]
            others[joined["online"]["seat"]] = player
        white.post('/api/game/say', {"text": "team plan", "to": "team"})
        white.post('/api/game/say', {"text": "hello all", "to": "all"})
        self.assertEqual([m["text"] for m in others["white2"].state()["online"]["chat"]], ["team plan", "hello all"])
        self.assertEqual([m["text"] for m in others["black2"].state()["online"]["chat"]], ["hello all"])
        refused = white.post('/api/game/say', {"move": {"from": [4, 1, 0], "to": [4, 3, 0]}, "to": "all"}).get_json()
        self.assertEqual(refused["error"], "Moves are suggested to your teammate only")

    def test_every_phrase_fits(self):
        self.assertTrue(all(len(phrase) <= 40 for phrase in PHRASES))


class TestClaiming(LobbyTestCase):
    def test_the_game_can_be_claimed_once_the_opponent_is_gone(self):
        white, black = self.two_players()
        white.move([4, 1, 0], [4, 3, 0])
        self.time.tick(ABANDON_SECONDS - 5)
        black.state()
        self.time.tick(10)
        online = white.state()["online"]
        self.assertFalse(online["claimable"])            # black was here 10 seconds ago
        self.assertEqual(online["away"], {"black": 10})
        self.assertEqual(white.post('/api/game/claim').get_json()["error"], "Your opponent has not left the game")
        self.time.tick(ABANDON_SECONDS)
        self.assertTrue(white.state()["online"]["claimable"])
        won = white.post('/api/game/claim').get_json()
        self.assertEqual((won["status"], won["winner"]), ("abandoned", "white"))

    def test_nobody_claims_a_game_still_waiting_for_players_or_by_watching(self):
        creator = self.open_game()
        self.time.tick(ABANDON_SECONDS + 1)
        self.assertFalse(creator.state()["online"]["claimable"])
        white, _ = self.two_players()
        self.time.tick(ABANDON_SECONDS + 1)
        self.assertFalse(Player(white.game_id).state()["online"]["claimable"])

    def test_a_claimed_game_replays_on_the_next_server(self):
        white, black = self.two_players()
        self.time.tick(ABANDON_SECONDS + 1)
        white.post('/api/game/claim')
        room = rooms.get(white.game_id)
        copy = handoff.restore(Rooms(), json.loads(json.dumps(handoff.snapshot(room))))
        self.assertEqual(copy.manager.get_state()["status"], "abandoned")


class TestCounts(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def counts(self):
        return self.client.get('/api/admin').get_json()["days"]

    def today(self):
        return list(self.counts().values())[-1]

    def test_games_are_counted_by_kind_and_when_they_end(self):
        before = self.today()
        data = self.client.post('/api/games', json={"kind": "computer", "computer": {"color": "black", "level": "easy"},
                                                    "dynamite": "classic"}).get_json()
        self.client.post(f'/api/game/resign?game={data["game_id"]}', json={})
        self.client.get(f'/api/game/state?game={data["game_id"]}')   # the end is counted once
        after = self.today()
        for name in ("games.started", "games.kind.computer", "games.level.easy", "games.dynamite.classic",
                     "games.finished", "games.ending.resigned", "computer.easy.lost"):
            self.assertEqual(after.get(name, 0) - before.get(name, 0), 1, name)

    def test_pages_and_visitors(self):
        before = self.today()
        self.assertTrue(self.client.post('/api/visit', json={"page": "lobby"}).get_json()["success"])
        self.client.post('/api/visit', json={"page": "home"})
        self.assertFalse(self.client.post('/api/visit', json={"page": "elsewhere"}).get_json()["success"])
        after = self.today()
        self.assertEqual(after["page.lobby"] - before.get("page.lobby", 0), 1)
        self.assertGreaterEqual(after["visitors"], 1)
        self.assertEqual(after["visitors"], max(before.get("visitors", 0), 1))   # the same visitor once a day

    def test_counts_carry_over_to_the_next_server_without_counting_twice(self):
        old, new = Stats(salt=b"s"), Stats(salt=b"s")
        old.count("games.started", 3)
        old.visitor("1.2.3.4")
        new.take(old.snapshot())          # pulled as the new server starts
        new.count("games.started")        # a game started on the new server
        new.visitor("1.2.3.4")            # the same visitor: not again
        old.count("games.started")        # a last game on the old one
        new.take(old.snapshot())          # pushed as the old one stops
        day = list(new.days().values())[-1]
        self.assertEqual((day["games.started"], day["visitors"]), (5, 1))


class TestFeedbackAndAdmin(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_feedback_reaches_the_admin_page(self):
        sent = self.client.post('/api/feedback', json={"kind": "idea", "text": " More clouds! ", "page": "/game/x"})
        self.assertTrue(sent.get_json()["success"])
        item = self.client.get('/api/admin').get_json()["feedback"][-1]
        self.assertEqual((item["kind"], item["text"], item["done"]), ("idea", "More clouds!", False))
        marked = self.client.post('/api/admin/feedback', json={"id": item["id"], "done": True}).get_json()
        self.assertTrue(next(each for each in marked["feedback"] if each["id"] == item["id"])["done"])

    def test_empty_or_unknown_feedback_is_refused(self):
        self.assertFalse(self.client.post('/api/feedback', json={"kind": "idea", "text": "  "}).get_json()["success"])
        self.assertFalse(self.client.post('/api/feedback', json={"kind": "rant", "text": "x"}).get_json()["success"])

    def test_the_admin_page_needs_its_key(self):
        with unittest.mock.patch.dict(os.environ, {"REALMCHESS_ADMIN_KEY": "letmein"}):
            self.assertEqual(self.client.get('/api/admin').status_code, 403)
            self.assertEqual(self.client.get('/api/admin', headers={"X-Admin-Key": "wrong"}).status_code, 403)
            self.assertEqual(self.client.get('/api/admin', headers={"X-Admin-Key": "letmein"}).status_code, 200)
            self.assertEqual(self.client.post('/api/admin/feedback', json={}).status_code, 403)
        app.config["PRODUCTION"] = True
        try:
            with unittest.mock.patch.dict(os.environ, {"REALMCHESS_ADMIN_KEY": ""}):
                self.assertEqual(self.client.get('/api/admin').status_code, 403)   # hosted without a key: closed
        finally:
            app.config["PRODUCTION"] = False

    def test_feedback_carries_over_and_handled_stays_handled(self):
        old, new = Inbox(), Inbox()
        item = old.add("bug", "the board froze")
        new.take(old.snapshot())
        new.mark(item["id"], True)
        new.take(old.snapshot())   # the old server's copy is not handled yet
        self.assertEqual([(each["text"], each["done"]) for each in new.items()], [("the board froze", True)])

    def test_the_handoff_carries_counts_and_feedback(self):
        with unittest.mock.patch.dict(os.environ, {"REALMCHESS_HANDOFF_KEY": "k"}):
            stats.count("test.handoff")
            inbox.add("other", "hello from the old server")
            data = self.client.get('/api/handoff', headers={"X-Handoff-Key": "k"}).get_json()
        self.assertIn("test.handoff", list(data["stats"]["days"].values())[-1])
        self.assertIn("hello from the old server", [item["text"] for item in data["feedback"]])


if __name__ == '__main__':
    unittest.main()
