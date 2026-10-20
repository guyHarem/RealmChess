"""
Choose the classic places of the special cells (portals, dynamite, clouds) by self-play.

    venv/bin/python tools/tune_layouts.py screen --candidates 24 --games 40     # 1. try random layouts
    venv/bin/python tools/tune_layouts.py match --layout tools/data/layouts.json --pick 0 --games 200
                                                                              # 2. the best one v none

Every candidate is mirrored for the two sides (like the shuffled layouts) and none can be
used on the first move: no first-move trip through a portal, no first-move blast. Step 1 plays
the computer (medium level) against itself on each and reports how often and how early each
kind of cell comes into play, how varied the openings are, and how White scores. Step 2 plays a
longer match with and without the special cells, to check balance and game length.

Everything is written under tools/data/, which is not part of the repository.
"""
import argparse
import json
import multiprocessing
import os
import random
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.levels import choose_move
from api.game_manager import GameManager
from engine import pieces
from engine.board import shuffled_clouds, shuffled_dynamite, shuffled_portals
from engine.game_state import GameState

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MAX_PLIES = 400


# ==================== CANDIDATES ====================

def first_move_uses(layout):
    """Could either side go through a portal or set off dynamite on its first move?"""
    for player in ("white", "black"):
        game = GameState()
        game.board.set_portals(layout["portals"])
        game.board.set_clouds(layout["clouds"])
        game.board.set_dynamite(layout["dynamite"])
        game.current_player = player
        for coord, _ in game.get_all_pieces_of_color(player):
            routes = game._legal_routes(coord)
            if any(routes.values()) or any(landing in game.board.dynamite for landing in routes):
                return True
    return False


def random_layout(rng):
    """Two portal pairs, four clouds and four charges, each mirrored, none on the first move"""
    while True:
        board = GameState().board
        portals = shuffled_portals(rng, board)
        board.set_portals(portals)
        clouds = shuffled_clouds(rng, board)
        board.set_clouds(clouds)
        dynamite = shuffled_dynamite(rng, board)
        layout = {"portals": [[list(a), list(b)] for a, b in portals],
                  "clouds": [list(cell) for cell in clouds],
                  "dynamite": [list(cell) for cell in dynamite]}
        if not first_move_uses(layout):
            return layout


# ==================== SELF-PLAY ====================

def play_one(job):
    """One medium-level game. Returns what happened, for the statistics."""
    layout, seed, level = job
    rng = random.Random(seed)
    manager = GameManager()
    if layout:
        manager.new_game(portals=layout["portals"], dynamite=layout["dynamite"], clouds=layout["clouds"])
    game = manager.game
    clouds = set(game.board.clouds)
    stats = {"trips": 0, "blasts": 0, "blasted": 0, "cloud_entries": 0, "first_use": None, "opening": None}
    for ply in range(MAX_PLIES):
        color = game.current_player
        choice = choose_move(game, level, rng=rng)
        if ply == 0:
            stats["opening"] = [list(choice.from_coord), list(choice.to_coord)]
        used = choice.to_coord in clouds
        response = manager.make_move(choice.from_coord, choice.to_coord)
        if response["success"] and response["pending_promotion"] is not None:
            response = manager.promote_pawn(choice.to_coord, getattr(pieces, choice.promotion)(color))
        entry = next(e for e in reversed(game.move_history) if e.get("special_move") != "promotion")
        stats["cloud_entries"] += used
        if entry.get("via"):
            stats["trips"] += 1
            used = True
        if entry.get("blast") is not None:
            stats["blasts"] += 1
            stats["blasted"] += len(entry["blast"])
            used = True
        if used and stats["first_use"] is None:
            stats["first_use"] = ply + 1
        if response["status"] not in ("ongoing", "check"):
            stats.update(plies=ply + 1, winner=response["winner"], ending=response["draw_reason"] or response["status"])
            return stats
    stats.update(plies=MAX_PLIES, winner=None, ending="too long")
    return stats


def summary(results):
    n = len(results)
    white = sum(1 if r["winner"] == "white" else 0.5 if r["winner"] is None else 0 for r in results) / n
    firsts = [r["first_use"] for r in results if r["first_use"]]
    return {
        "games": n,
        "white_score": round(white, 3),
        "moves_each": round(statistics.mean(r["plies"] for r in results) / 2, 1),
        "trips": round(sum(r["trips"] for r in results) / n, 2),
        "blasts": round(sum(r["blasts"] for r in results) / n, 2),
        "blasted": round(sum(r["blasted"] for r in results) / n, 2),
        "cloud_entries": round(sum(r["cloud_entries"] for r in results) / n, 2),
        "unused_games": sum(1 for r in results if r["first_use"] is None),
        "first_use_move": round(statistics.median(firsts) / 2, 1) if firsts else None,
        "openings": len({json.dumps(r["opening"]) for r in results}),
        "top_opening_share": round(Counter(json.dumps(r["opening"]) for r in results).most_common(1)[0][1] / n, 2),
        "draws": sum(1 for r in results if r["winner"] is None),
    }


def fitness(s):
    """Higher is better: every kind of cell used a few times a game, from early on but not at
    once, varied openings, and White's score near even"""
    def near(value, low, high):
        return 1.0 if low <= value <= high else max(0.0, 1 - min(abs(value - low), abs(value - high)) / high)
    first = s["first_use_move"] or 99
    return round(
        near(s["trips"], 2, 6) + near(s["blasts"], 0.8, 2.5) + near(s["cloud_entries"], 1.5, 6)
        + near(first, 3, 15) + (1 - s["unused_games"] / s["games"])
        + (1 - s["top_opening_share"]) - 2 * abs(s["white_score"] - 0.5), 3)


# ==================== COMMANDS ====================

def screen(args):
    rng = random.Random(args.seed)
    layouts = [random_layout(rng) for _ in range(args.candidates)]
    if args.include:
        with open(args.include, encoding="utf-8") as f:
            layouts = json.load(f) + layouts
    scored = []
    started = time.perf_counter()
    with multiprocessing.Pool() as pool:
        for index, layout in enumerate(layouts):
            batch = pool.map(play_one, [(layout, 1000 + game, "medium") for game in range(args.games)])
            s = summary(batch)
            s["fitness"] = fitness(s)
            scored.append({"layout": layout, "summary": s})
            print(f"layout {index} ({time.perf_counter() - started:.0f}s): {json.dumps(s)}", flush=True)
    scored.sort(key=lambda row: -row["summary"]["fitness"])
    os.makedirs(DATA, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(scored, f, indent=1)
    print(f"\nSaved to {args.out}. Best:")
    for row in scored[:5]:
        print(json.dumps(row["summary"]), json.dumps(row["layout"]))


def match(args):
    with open(args.layout, encoding="utf-8") as f:
        layout = json.load(f)[args.pick]["layout"]
    print("layout", json.dumps(layout))
    with multiprocessing.Pool() as pool:
        for name, chosen in (("none", None), ("special cells", layout)):
            batch = pool.map(play_one, [(chosen, 5000 + game, args.level) for game in range(args.games)])
            print(f"{name}: {json.dumps(summary(batch))}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("screen")
    command.add_argument("--candidates", type=int, default=24)
    command.add_argument("--games", type=int, default=40)
    command.add_argument("--seed", type=int, default=1)
    command.add_argument("--include", help="a JSON list of layouts to try as well")
    command.add_argument("--out", default=os.path.join(DATA, "layouts.json"))
    command = commands.add_parser("match")
    command.add_argument("--layout", default=os.path.join(DATA, "layouts.json"))
    command.add_argument("--pick", type=int, default=0)
    command.add_argument("--games", type=int, default=200)
    command.add_argument("--level", default="medium")
    args = parser.parse_args()
    {"screen": screen, "match": match}[args.command](args)


if __name__ == "__main__":
    main()
