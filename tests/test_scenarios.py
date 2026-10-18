"""
The scenarios live in the frontend (realmchess-frontend/src/scenarios.json, written by
tools/generate_scenarios.py). This re-checks every one against the engine: the position is
legal, the stored solution works move by move, and it is the only solution.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from api.game_manager import GameManager  # noqa: E402
from generate_scenarios import forced_mate_in_two, mating_moves  # noqa: E402

SCENARIOS_PATH = os.path.join(ROOT, "realmchess-frontend", "src", "scenarios.json")


def pair(move):
    return tuple(move["from"]), tuple(move["to"])


class TestScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCENARIOS_PATH, encoding="utf-8") as f:
            cls.tiers = json.load(f)["tiers"]

    def scenarios(self):
        for tier in self.tiers:
            for scenario in tier["scenarios"]:
                yield tier, scenario

    def setup(self, tier, scenario):
        manager = GameManager()
        pieces = [{"coord": tuple(p["coord"]), "type": p["type"], "color": p["color"]} for p in scenario["pieces"]]
        board = tier["board"]
        response = manager.setup_position(pieces, "white", rocks=tier["rocks"],
                                          size=board["size"], z_min=board["z_min"], z_max=board["z_max"])
        self.assertTrue(response["success"], response.get("error"))
        return manager

    def test_collection_shape(self):
        self.assertEqual([tier["id"] for tier in self.tiers], ["beginner", "intermediate", "advanced", "expert"])
        ids = [scenario["id"] for _, scenario in self.scenarios()]
        self.assertEqual(len(ids), len(set(ids)))
        for tier in self.tiers:
            self.assertGreaterEqual(len(tier["scenarios"]), 4, tier["id"])
            self.assertIn(tier["mateIn"], (1, 2))

    def test_positions_are_legal_and_open_on_the_right_layer(self):
        for tier, scenario in self.scenarios():
            with self.subTest(scenario["id"]):
                manager = self.setup(tier, scenario)
                game = manager.game
                self.assertIsNotNone(game.white_king_pos)
                self.assertIsNotNone(game.black_king_pos)
                self.assertFalse(game.is_in_check("black"), "Black is in check with White to move")
                self.assertFalse(game.is_in_check("white"))
                self.assertEqual(scenario["layer"], scenario["solution"]["key"]["from"][2])

    def test_stored_solution_plays_out_to_checkmate(self):
        for tier, scenario in self.scenarios():
            solution = scenario["solution"]
            if tier["mateIn"] == 1:
                with self.subTest(scenario["id"]):
                    manager = self.setup(tier, scenario)
                    response = manager.make_move(*pair(solution["key"]))
                    self.assertEqual((response["status"], response["winner"]), ("checkmate", "white"))
                continue
            self.assertTrue(solution["mates"], scenario["id"])
            for mate in solution["mates"]:
                with self.subTest(scenario["id"], mate=mate):
                    manager = self.setup(tier, scenario)
                    response = manager.make_move(*pair(solution["key"]))
                    self.assertTrue(response["success"], response.get("error"))
                    self.assertNotEqual(response["status"], "checkmate")
                    response = manager.make_move(*pair(solution["reply"]))
                    self.assertTrue(response["success"], response.get("error"))
                    response = manager.make_move(*pair(mate))
                    self.assertEqual((response["status"], response["winner"]), ("checkmate", "white"))

    def test_the_solution_is_the_only_one(self):
        for tier, scenario in self.scenarios():
            with self.subTest(scenario["id"]):
                game = self.setup(tier, scenario).game
                solution = scenario["solution"]
                mates = mating_moves(game)
                if tier["mateIn"] == 1:
                    self.assertEqual(mates, [pair(solution["key"])])
                    continue
                self.assertEqual(mates, [], "a mate in one exists in a mate-in-two scenario")
                keys = forced_mate_in_two(game)
                self.assertEqual(list(keys), [pair(solution["key"])])
                # Every defence loses, and the stored list is every mating move after the stored reply
                answers = keys[pair(solution["key"])]
                self.assertTrue(all(answers.values()))
                self.assertEqual(sorted(answers[pair(solution["reply"])]), sorted(pair(m) for m in solution["mates"]))


if __name__ == '__main__':
    unittest.main()
