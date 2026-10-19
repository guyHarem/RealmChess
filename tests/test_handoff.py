"""
Handing games to the next server on a deploy (api/handoff.py): a game replays move for move,
with its seats, clocks and offer, and a real stopping server sends its games over.
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
import unittest.mock
import urllib.request

from api import handoff
from api.rooms import Rooms
from engine.pieces import Queen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def play(manager, *moves):
    for from_coord, to_coord in moves:
        response = manager.make_move(from_coord, to_coord)
        assert response["success"], response["error"]


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.old, self.new = Rooms(), Rooms()

    def travel(self, room):
        data = json.loads(json.dumps(handoff.snapshot(room)))   # only JSON crosses over
        return handoff.restore(self.new, data)

    def test_an_online_game_arrives_as_it_was(self):
        room = self.old.create("online")
        room.manager.new_game(move_limit=40, clock={"initial": 300, "increment": 2})
        white, black = room.sit("white"), room.sit("black")
        play(room.manager, ((4, 1, 0), (4, 3, 0)), ((4, 6, 0), (4, 4, 0)), ((1, 1, 2), (1, 3, 0)))
        room.make_offer("black", "draw")
        before = room.manager.get_state()

        copy = self.travel(room)
        after = copy.manager.get_state()
        self.assertEqual(copy.id, room.id)
        self.assertEqual(after["board"].keys(), before["board"].keys())
        self.assertEqual([str(after["board"][c]) for c in after["board"]], [str(before["board"][c]) for c in after["board"]])
        self.assertEqual(after["move_history"], before["move_history"])
        self.assertEqual(after["current_player"], "black")
        self.assertEqual(after["move_limit"], 40)
        self.assertAlmostEqual(after["clock"]["black"], before["clock"]["black"], delta=1)
        self.assertEqual(after["clock"]["running"], "black")
        self.assertGreater(after["version"], before["version"])
        self.assertEqual((copy.color_of(white), copy.color_of(black)), ("white", "black"))
        self.assertEqual(copy.offer, {"kind": "draw", "by": "black"})

    def test_a_team_game_keeps_its_seats_and_turn(self):
        room = self.old.create("online")
        room.teams = True
        keys = {seat: room.sit(seat) for seat in ("white", "black", "white2", "black2")}
        play(room.manager, ((4, 1, 0), (4, 3, 0)), ((4, 6, 0), (4, 4, 0)))
        copy = self.travel(room)
        self.assertTrue(copy.teams)
        self.assertEqual({seat: copy.seat_of(key) for seat, key in keys.items()}, {seat: seat for seat in keys})
        self.assertEqual(copy.turn_seat(), "white2")

    def test_the_game_goes_on_and_can_be_taken_back(self):
        room = self.old.create("local")
        room.manager.new_game(rocks=False, clock={"initial": 60, "increment": 0})
        play(room.manager, ((4, 1, 0), (4, 3, 0)), ((4, 6, 0), (4, 4, 0)))
        copy = self.travel(room)
        self.assertEqual(sum(1 for p in copy.manager.get_state()["board"].values() if str(p) == "Rock()"), 0)
        self.assertTrue(copy.manager.undo_move()["success"])
        self.assertEqual(len(copy.manager.game.move_history), 1)
        play(copy.manager, ((3, 6, 0), (3, 4, 0)))
        self.assertEqual(copy.manager.get_state()["current_player"], "white")

    def test_a_promotion_replays(self):
        room = self.old.create("local")
        manager = room.manager
        # Walk a Space pawn up the b file: nothing stands in its way there except Black's Space pawn
        play(manager, ((1, 1, 2), (1, 3, 2)), ((6, 6, 2), (6, 4, 2)), ((1, 3, 2), (1, 4, 2)), ((6, 4, 2), (6, 3, 2)),
             ((1, 4, 2), (1, 5, 1)), ((6, 3, 2), (6, 2, 2)), ((1, 5, 1), (0, 6, 0)), ((7, 6, 0), (7, 5, 0)),
             ((0, 6, 0), (1, 7, 0)))
        self.assertEqual(manager.game.pending_promotion, (1, 7, 0))
        self.assertTrue(manager.promote_pawn((1, 7, 0), Queen("white"))["success"])
        before = manager.get_state()
        copy = self.travel(room)
        self.assertEqual(copy.manager.get_state()["move_history"], before["move_history"])

    def test_hand_edited_positions_and_practice_boards_stay_behind(self):
        practice = self.old.create("practice")
        practice.manager.new_game()
        edited = self.old.create("local")
        edited.manager.remove_piece((0, 0, 0))
        self.assertIsNone(handoff.snapshot(practice))
        self.assertIsNone(handoff.snapshot(edited))

    def test_a_newer_copy_replaces_one_taken_over_earlier(self):
        room = self.old.create("local")
        play(room.manager, ((4, 1, 0), (4, 3, 0)))
        arrival = handoff.Arrival()
        early = json.loads(json.dumps(handoff.snapshot(room)))
        self.assertEqual(arrival.take(self.new, {"rooms": [early]}, how="pulled", log=lambda _: None), 1)
        play(room.manager, ((4, 6, 0), (4, 4, 0)))   # a move on the old server in between
        late = json.loads(json.dumps(handoff.snapshot(room)))
        self.assertEqual(arrival.take(self.new, {"rooms": [late], "done": True}, log=lambda _: None), 1)
        self.assertEqual(len(self.new.get(room.id).manager.game.move_history), 2)
        self.assertEqual(arrival.counts, {"pulled": 1, "pushed": 1})
        # The same copy again, or an older one, changes nothing
        self.assertEqual(arrival.take(self.new, {"rooms": [early, late]}, log=lambda _: None), 0)

    def test_moves_made_here_are_not_overwritten(self):
        room = self.old.create("local")
        play(room.manager, ((4, 1, 0), (4, 3, 0)))
        arrival = handoff.Arrival()
        arrival.take(self.new, {"rooms": [json.loads(json.dumps(handoff.snapshot(room)))]}, log=lambda _: None)
        play(self.new.get(room.id).manager, ((3, 6, 0), (3, 4, 0)))   # played here after the switch
        play(room.manager, ((4, 6, 0), (4, 4, 0)))
        stale = json.loads(json.dumps(handoff.snapshot(room)))
        self.assertEqual(arrival.take(self.new, {"rooms": [stale]}, log=lambda _: None), 0)
        self.assertEqual(self.new.get(room.id).manager.game.move_history[-1]["to"], (3, 4, 0))

    def test_sending_tries_again_while_it_reaches_itself(self):
        room = self.old.create("local")
        play(room.manager, ((4, 1, 0), (4, 3, 0)))
        answers = iter([{"self": True}, {"self": True}, {"restored": 1}])
        with unittest.mock.patch.dict(os.environ, {"REALMCHESS_HANDOFF_KEY": "k"}), \
                unittest.mock.patch.object(handoff, "_call", lambda url, body=None: next(answers)):
            self.assertEqual(handoff.send(self.old, url="http://new", log=lambda _: None, pause=0), 1)

    def test_a_game_that_does_not_replay_is_dropped(self):
        room = self.old.create("local")
        play(room.manager, ((4, 1, 0), (4, 3, 0)))
        data = json.loads(json.dumps(handoff.snapshot(room)))
        data["moves"][0]["to"] = [4, 5, 0]   # not a legal move
        arrival = handoff.Arrival()
        self.assertEqual(arrival.take(self.new, {"rooms": [data], "done": True}, log=lambda _: None), 0)
        self.assertIsNone(self.new.get(room.id))
        self.assertTrue(arrival.done.is_set())


class TestRealServers(unittest.TestCase):
    """Two real servers: the first is stopped like a host does on a deploy and hands over"""

    def start(self, port, env):
        server = subprocess.Popen(
            [sys.executable, "-c", f"import serve; serve.start('127.0.0.1', {port}, thinkers=1)"], cwd=ROOT,
            env={**os.environ, "REALMCHESS_TRUST_PROXY": "0", "REALMCHESS_HANDOFF_KEY": "test-key",
                 "REALMCHESS_HANDOFF_PATIENCE": "3", **env},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (server.poll() is None and server.terminate(), server.wait(timeout=20)))
        for _ in range(100):
            try:
                self.call(port, "/api/health")
                return server
            except OSError:
                time.sleep(0.1)
        self.fail("The server did not start")

    @staticmethod
    def free_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    @staticmethod
    def call(port, path, body=None, seat=None):
        headers = {"Content-Type": "application/json"}
        if seat:
            headers["X-Seat"] = seat
        request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as answer:
                return json.loads(answer.read())
        except urllib.error.HTTPError as e:
            with e:
                return json.loads(e.read())

    def test_a_deploy_keeps_the_online_game(self):
        # The public address leads to the old server until the new one is up (the new one pulls
        # from there), and to the new one by the time the old one stops (it pushes there)
        old_port, new_port = self.free_port(), self.free_port()
        old = self.start(old_port, {"REALMCHESS_HANDOFF_URL": f"http://127.0.0.1:{new_port}"})
        created = self.call(old_port, "/api/games", {"kind": "online", "clock": {"initial": 300, "increment": 0}})
        game, white = created["game_id"], created["seat"]
        black = self.call(old_port, f"/api/game/join?game={game}", {})["seat"]
        self.assertTrue(self.call(old_port, f"/api/game/move?game={game}", {"from": [4, 1, 0], "to": [4, 3, 0]}, white)["success"])

        self.start(new_port, {"REALMCHESS_HANDOFF_URL": f"http://127.0.0.1:{old_port}"})
        self.assertEqual(self.call(new_port, "/api/health")["taken_over"], {"pulled": 1, "pushed": 0})
        # A move still reaches the old server before the switch
        self.assertTrue(self.call(old_port, f"/api/game/move?game={game}", {"from": [4, 6, 0], "to": [4, 4, 0]}, black)["success"])

        old.send_signal(signal.SIGTERM)
        self.assertEqual(old.wait(timeout=40), 0)
        self.assertEqual(self.call(new_port, "/api/health")["taken_over"], {"pulled": 1, "pushed": 1})

        state = self.call(new_port, f"/api/game/state?game={game}", seat=white)
        self.assertTrue(state["success"], state)
        self.assertEqual((state["online"]["you"], state["current_player"], len(state["move_history"])), ("white", "white", 2))
        moved = self.call(new_port, f"/api/game/move?game={game}", {"from": [3, 1, 0], "to": [3, 3, 0]}, white)
        self.assertTrue(moved["success"], moved)

    def test_the_handoff_needs_the_key(self):
        port = self.free_port()
        self.start(port, {})
        answer = self.call(port, "/api/handoff", {"rooms": [], "done": True})
        self.assertFalse(answer["success"])


if __name__ == '__main__':
    unittest.main()
