"""
Finds checkmate puzzles for the scenario player by trial: build a random position, and keep
it only if White has exactly one way to force mate in the asked number of moves.

    python tools/generate_scenarios.py            # regenerate realmchess-frontend/src/scenarios.json

Every puzzle it writes is re-checked by tests/test_scenarios.py.
"""
import json
import os
import random
import sys
import time
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.game_state import GameState  # noqa: E402
from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn, Rock  # noqa: E402

OUT = os.path.join(ROOT, "realmchess-frontend", "src", "scenarios.json")
SMALL = {"size": 5, "z_min": -1, "z_max": 1}
FULL = {"size": 8, "z_min": -2, "z_max": 2}
CLASSES = {"Queen": Queen, "Rook": Rook, "Bishop": Bishop, "Knight": Knight, "Pawn": Pawn}

# name, board, mate in N, how many puzzles, seconds to spend looking
TIERS = [
    ("beginner", "Beginner", "Small board. One move is checkmate.", SMALL, 1, 8, 20),
    ("intermediate", "Intermediate", "Small board. Checkmate in two moves.", SMALL, 2, 8, 60),
    ("advanced", "Advanced", "Full board, all five layers. One move is checkmate.", FULL, 1, 8, 30),
    ("expert", "Expert", "Full board. Checkmate in two moves.", FULL, 2, 8, 300),
]


def all_moves(game, color):
    return [(coord, move) for coord, _ in game.get_all_pieces_of_color(color) for move in game.get_legal_moves(coord)]


def mating_moves(game):
    """White moves that checkmate at once"""
    mates = []
    for coord, move in all_moves(game, "white"):
        game.make_move(coord, move)
        if game.is_in_check("black") and game.is_checkmate("black"):
            mates.append((coord, move))
        game.undo_move()
    return mates


def forced_mate_in_two(game):
    """First moves after which every black reply allows a mate. Returns {key: {reply: [mates]}}"""
    keys = {}
    for coord, move in all_moves(game, "white"):
        game.make_move(coord, move)
        replies = all_moves(game, "black")
        answers = {}
        # No replies means stalemate or mate in one: neither is a mate in two
        forced = bool(replies)
        for reply in replies:
            game.make_move(*reply)
            mates = mating_moves(game)
            game.undo_move()
            if not mates:
                forced = False
                break
            answers[reply] = mates
        game.undo_move()
        if forced:
            keys[(coord, move)] = answers
    return keys


def random_position(rng, bounds):
    size, z_min, z_max = bounds["size"], bounds["z_min"], bounds["z_max"]
    full = size == 8
    game = GameState(size=size, z_min=z_min, z_max=z_max)
    board = game.board.board
    if full:
        for coord in [c for c, p in board.items() if not isinstance(p, Rock)]:
            del board[coord]

    def cell(edge_bias=0.0):
        def axis():
            return rng.choice([0, size - 1]) if rng.random() < edge_bias else rng.randrange(size)
        z = rng.choice([z_min, z_max]) if rng.random() < edge_bias else rng.randint(z_min, z_max)
        return (axis(), axis(), z)

    def place(piece, edge_bias=0.0, near=None):
        for _ in range(60):
            coord = cell(edge_bias)
            if near is not None:
                coord = tuple(min(hi, max(lo, n + rng.randint(-3, 3)))
                              for n, lo, hi in zip(near, (0, 0, z_min), (size - 1, size - 1, z_max)))
            if coord in board:
                continue
            if isinstance(piece, Pawn) and not 2 <= coord[1] <= size - 2:
                continue
            board[coord] = piece
            return coord
        return None

    black_king = place(King("black"), edge_bias=0.8)
    place(King("white"), near=black_king if rng.random() < 0.5 else None)
    for _ in range(rng.choice([2, 2, 3, 3] if not full else [2, 3, 3, 4])):
        kind = rng.choice(["Queen", "Rook", "Rook", "Bishop", "Knight", "Knight"])
        place(CLASSES[kind]("white"), near=black_king if rng.random() < 0.6 else None)
    for _ in range(rng.choice([0, 1, 1, 2])):
        kind = rng.choice(["Pawn", "Pawn", "Knight", "Bishop", "Rook"])
        place(CLASSES[kind]("black"), near=black_king)
    for piece in board.values():
        if hasattr(piece, "has_moved"):
            piece.has_moved = True
    game.current_player = "white"
    game.reset_tracking()
    return game


def to_list(coord):
    return [int(n) for n in coord]


def describe(game):
    return sorted(
        ({"coord": to_list(coord), "type": type(piece).__name__, "color": piece.color}
         for coord, piece in game.board.board.items() if not isinstance(piece, Rock)),
        key=lambda item: (item["color"], item["type"], item["coord"]))


def try_seed(args):
    seed, bounds, depth = args
    rng = random.Random(seed)
    game = random_position(rng, bounds)
    if game.white_king_pos is None or game.black_king_pos is None:
        return None
    # The side that is not to move may not be in check, and we keep White out of check too
    if game.is_in_check("black") or game.is_in_check("white"):
        return None
    layers = {coord[2] for coord, piece in game.board.board.items() if not isinstance(piece, Rock)}
    if len(layers) < 2:
        return None  # a puzzle on one layer is just ordinary chess

    mates = mating_moves(game)
    if depth == 1:
        if len(mates) != 1:
            return None
        (key_from, key_to), = mates
        solution = {"key": {"from": to_list(key_from), "to": to_list(key_to)}}
    else:
        if mates:
            return None
        keys = forced_mate_in_two(game)
        if len(keys) != 1:
            return None
        ((key_from, key_to), answers), = keys.items()
        if len(answers) < 2:
            return None
        # The defence shown is the one that leaves White the fewest ways to finish
        reply = min(answers, key=lambda r: (len(answers[r]), r))
        solution = {
            "key": {"from": to_list(key_from), "to": to_list(key_to)},
            "reply": {"from": to_list(reply[0]), "to": to_list(reply[1])},
            "mates": [{"from": to_list(a), "to": to_list(b)} for a, b in answers[reply]],
        }
    return {
        "seed": seed,
        "choices": len(all_moves(game, "white")),
        "layer": int(key_from[2]),
        "pieces": describe(game),
        "solution": solution,
    }


def find(pool, bounds, depth, wanted, budget, first_seed):
    found, seen, started, seed = [], set(), time.time(), first_seed
    batch = 400 if depth == 1 else 64
    while len(found) < wanted * 2 and time.time() - started < budget:
        jobs = [(s, bounds, depth) for s in range(seed, seed + batch)]
        seed += batch
        for puzzle in pool.imap_unordered(try_seed, jobs, chunksize=4):
            if puzzle is None:
                continue
            signature = json.dumps(puzzle["pieces"])
            if signature not in seen:
                seen.add(signature)
                found.append(puzzle)
        print(f"  mate in {depth}, {bounds['size']} wide: {len(found)} found after {seed - first_seed} tries, "
              f"{time.time() - started:.0f}s", flush=True)
    # Easiest first: fewer possible moves to look through
    found.sort(key=lambda puzzle: (puzzle["choices"], puzzle["seed"]))
    step = max(1, len(found) // wanted)
    return found[::step][:wanted]


def main():
    tiers = []
    with Pool() as pool:
        for index, (tier_id, name, note, bounds, depth, wanted, budget) in enumerate(TIERS):
            print(name, flush=True)
            puzzles = find(pool, bounds, depth, wanted, budget, first_seed=index * 10_000_000)
            tiers.append({
                "id": tier_id, "name": name, "note": note, "board": bounds, "rocks": bounds["size"] == 8,
                "mateIn": depth,
                "scenarios": [{"id": f"{tier_id}-{n}", "layer": p["layer"], "pieces": p["pieces"], "solution": p["solution"]}
                              for n, p in enumerate(puzzles, 1)],
            })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"tiers": tiers}, f, indent=1)
        f.write("\n")
    print("wrote", OUT, [len(t["scenarios"]) for t in tiers])


if __name__ == "__main__":
    main()
