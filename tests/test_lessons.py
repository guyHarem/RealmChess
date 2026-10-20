"""
The lessons live in the frontend (realmchess-frontend/src/lessons.json). This checks every
task against the real engine, so a lesson can never ask for a move the game would refuse.
"""
import json
import os
import unittest
from api.game_manager import GameManager

LESSONS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "realmchess-frontend", "src", "lessons.json")


class TestLessons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(LESSONS_PATH, encoding="utf-8") as f:
            cls.data = json.load(f)

    def steps(self):
        for lesson in self.data["lessons"]:
            for number, step in enumerate(lesson["steps"], 1):
                yield f"{lesson['id']} step {number}", step

    def board_of(self, name):
        lesson = next(lesson for lesson in self.data["lessons"] if name.startswith(lesson["id"] + " "))
        return lesson.get("board", self.data["board"])

    def setup(self, step, board=None):
        board = board or self.data["board"]
        manager = GameManager()
        pieces = [{"coord": tuple(p["coord"]), "type": p["type"], "color": p.get("color")} for p in step["pieces"]]
        portals = [[list(a), list(b)] for a, b in step.get("portals", [])] or None
        response = manager.setup_position(pieces, "white", rocks=False,
                                          size=board["size"], z_min=board["z_min"], z_max=board["z_max"],
                                          portals=portals, dynamite=step.get("dynamite"))
        self.assertTrue(response["success"], response.get("error"))
        return manager

    def test_lessons_have_content(self):
        self.assertGreaterEqual(len(self.data["lessons"]), 9)
        ids = [lesson["id"] for lesson in self.data["lessons"]]
        self.assertEqual(len(ids), len(set(ids)))
        for lesson in self.data["lessons"]:
            self.assertTrue(lesson["title"] and lesson["text"] and lesson["steps"], lesson["id"])

    def test_every_task_is_a_legal_move_with_the_promised_effect(self):
        for name, step in self.steps():
            with self.subTest(name):
                board = self.board_of(name)
                manager = self.setup(step, board)
                from_coord, to_coord = tuple(step["from"]), tuple(step["to"])
                self.assertIn(step["layer"], range(board["z_min"], board["z_max"] + 1))
                self.assertEqual(from_coord[2], step["layer"], "the lesson should open on the layer of its piece")

                legal = manager.get_legal_moves(from_coord)["legal_moves"]
                self.assertIn(to_coord, legal)
                target = manager.game.board.get_piece(to_coord)

                response = manager.make_move(from_coord, to_coord)
                self.assertTrue(response["success"], response.get("error"))
                if step["expect"] == "move":
                    self.assertIsNone(target)
                elif step["expect"] == "capture":
                    self.assertIsNotNone(target)
                    self.assertEqual(target.color, "black")
                elif step["expect"] == "blast":
                    self.assertEqual(manager.game.move_history[-1]["special_move"], "explosion")
                elif step["expect"] == "checkmate":
                    self.assertEqual(response["status"], "checkmate")
                    self.assertEqual(response["winner"], "white")
                else:
                    self.fail(f"unknown expectation {step['expect']}")

    def test_checkmate_lesson_has_only_one_mating_move(self):
        for name, step in self.steps():
            if step["expect"] != "checkmate":
                continue
            mates = []
            manager = self.setup(step)
            for coord, piece in manager.game.get_all_pieces_of_color("white"):
                for move in manager.game.get_legal_moves(coord):
                    trial = self.setup(step)
                    if trial.make_move(coord, move)["status"] == "checkmate":
                        mates.append((coord, move))
            self.assertEqual(mates, [(tuple(step["from"]), tuple(step["to"]))], name)


if __name__ == '__main__':
    unittest.main()
