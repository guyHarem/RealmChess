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
            env={**os.environ, "REALMCHESS_TRUST_PROXY": "0", "REALMCHESS_HANDOFF_KEY": "test-key", **env},
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
            return json.loads(e.read())

    def test_a_deploy_keeps_the_online_game(self):
        old_port, new_port = self.free_port(), self.free_port()
        new = self.start(new_port, {})
        old = self.start(old_port, {"REALMCHESS_HANDOFF_URL": f"http://127.0.0.1:{new_port}"})

        created = self.call(old_port, "/api/games", {"kind": "online", "clock": {"initial": 300, "increment": 0}})
        game, white = created["game_id"], created["seat"]
        black = self.call(old_port, f"/api/game/join?game={game}", {})["seat"]
        self.assertTrue(self.call(old_port, f"/api/game/move?game={game}", {"from": [4, 1, 0], "to": [4, 3, 0]}, white)["success"])

        old.send_signal(signal.SIGTERM)
        self.assertEqual(old.wait(timeout=20), 0)

        state = self.call(new_port, f"/api/game/state?game={game}", seat=black)
        self.assertTrue(state["success"], state)
        self.assertEqual((state["online"]["you"], state["current_player"], len(state["move_history"])), ("black", "black", 1))
        moved = self.call(new_port, f"/api/game/move?game={game}", {"from": [4, 6, 0], "to": [4, 4, 0]}, black)
        self.assertTrue(moved["success"], moved)

    def test_the_handoff_needs_the_key(self):
        port = self.free_port()
        self.start(port, {})
        answer = self.call(port, "/api/handoff", {"rooms": [], "done": True})
        self.assertFalse(answer["success"])


if __name__ == '__main__':
    unittest.main()
