"""
Move tables for one board size, built once and shared by every FastBoard of that size.

Squares are numbered 0..n-1 (x first, then y, then layer). For each square the tables say
where each kind of piece can go on an empty board. They are generated from the piece
classes in engine/pieces.py, so the shapes of the moves cannot drift from the real rules.
"""
import random

from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn

EMPTY, PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, ROCK = range(8)
WHITE, BLACK = 0, 8   # colour bit: white pieces are 1-6, black pieces 9-14
UNMOVED = 16          # extra bit on a pawn, rook or king that has never moved

_CACHE = {}


def tables_for(size, z_min, z_max):
    key = (size, z_min, z_max)
    if key not in _CACHE:
        _CACHE[key] = Tables(size, z_min, z_max)
    return _CACHE[key]


def _sign(value):
    return (value > 0) - (value < 0)


class Tables:
    def __init__(self, size, z_min, z_max):
        self.size, self.z_min, self.z_max = size, z_min, z_max
        self.bounds = bounds = (size, z_min, z_max)
        self.coords = [(x, y, z) for z in range(z_min, z_max + 1) for y in range(size) for x in range(size)]
        self.index = {coord: i for i, coord in enumerate(self.coords)}
        self.n = n = len(self.coords)
        index = self.index

        def lines(piece):
            """A sliding piece's squares, grouped into lines that run outward from each square"""
            table = []
            for coord in self.coords:
                by_direction = {}
                for target in piece.get_possible_moves(coord, bounds):
                    delta = tuple(t - c for t, c in zip(target, coord))
                    by_direction.setdefault(tuple(_sign(d) for d in delta), []).append((max(map(abs, delta)), target))
                table.append(tuple(tuple(index[target] for _, target in sorted(squares))
                                   for squares in by_direction.values()))
            return table

        def jumps(piece):
            return [tuple(index[target] for target in piece.get_possible_moves(coord, bounds)) for coord in self.coords]

        # slides[BISHOP], slides[ROOK], slides[QUEEN]: for each square, a tuple of lines
        self.slides = [None] * 8
        self.slides[BISHOP] = lines(Bishop("white"))
        self.slides[ROOK] = lines(Rook("white"))
        self.slides[QUEEN] = lines(Queen("white"))
        self.knight = jumps(Knight("white"))
        self.king = jumps(King("white"))          # where the king can step
        # ... where it can capture but not step, and everything it attacks
        king = King("white")
        self.king_takes = [tuple(index[target] for target in king.get_capture_only_moves(coord, bounds))
                           for coord in self.coords]
        self.king_attacks = [self.king[square] + self.king_takes[square] for square in range(len(self.coords))]

        # Along the rank in each direction (for castling): row[square] = (towards +x, towards -x)
        self.row = []
        for x, y, z in self.coords:
            self.row.append((tuple(index[(i, y, z)] for i in range(x + 1, size)),
                             tuple(index[(i, y, z)] for i in range(x - 1, -1, -1))))

        # Pawns, per colour (0 white, 1 black)
        self.pawn_steps = ([], [])       # one square forward (straight, or climbing/descending a layer)
        self.pawn_doubles = ([], [])     # (destination, square passed over) for the first-move double step
        self.pawn_captures = ([], [])
        self.pawn_attackers = ([[] for _ in range(n)], [[] for _ in range(n)])  # where a pawn attacking here stands
        self.promotes = ([], [])         # True on that colour's last rank
        for colour, name in enumerate(("white", "black")):
            last_rank = size - 1 if name == "white" else 0
            for square, coord in enumerate(self.coords):
                moves, captures = Pawn(name).get_possible_moves(coord, bounds)
                steps, doubles = [], []
                for target in moves:
                    if abs(target[1] - coord[1]) == 1:
                        steps.append(index[target])
                    else:
                        middle = tuple((a + b) // 2 for a, b in zip(coord, target))
                        doubles.append((index[target], index[middle]))
                self.pawn_steps[colour].append(tuple(steps))
                self.pawn_doubles[colour].append(tuple(doubles))
                self.pawn_captures[colour].append(tuple(index[target] for target in captures))
                for target in captures:
                    self.pawn_attackers[colour][index[target]].append(square)
                self.promotes[colour].append(coord[1] == last_rank)

        # Squares on a straight or diagonal line with each square: only pieces standing there
        # can be shielding a king on that square
        self.aligned = [frozenset(target for line in self.slides[QUEEN][square] for target in line)
                        for square in range(n)]
        # line_to[a][b] = (is it a rook line?, the whole line from a that passes through b)
        self.line_to = []
        for square in range(n):
            entry = {}
            for kind, straight in ((ROOK, True), (BISHOP, False)):
                for line in self.slides[kind][square]:
                    for target in line:
                        entry[target] = (straight, line)
            self.line_to.append(entry)
        self.knight_set = [frozenset(squares) for squares in self.knight]
        self.pawn_attacker_set = tuple([frozenset(squares) for squares in table] for table in self.pawn_attackers)

        # Random numbers for position fingerprints (Zobrist hashing); fixed seed so runs repeat
        rng = random.Random(20261009)
        self.z_piece = [[rng.getrandbits(64) for _ in range(n)] for _ in range(16)]
        self.z_black_to_move = rng.getrandbits(64)
        self.z_castle = [rng.getrandbits(64) for _ in range(n)]
        self.z_en_passant = [rng.getrandbits(64) for _ in range(n)]
        self.z_dynamite = [rng.getrandbits(64) for _ in range(n)]
        # Each square's 3x3x3 cube (itself included), for dynamite blasts
        self.cube = [tuple(index[(x2, y2, z2)]
                           for z2 in range(max(z - 1, z_min), min(z + 1, z_max) + 1)
                           for y2 in range(max(y - 1, 0), min(y + 1, size - 1) + 1)
                           for x2 in range(max(x - 1, 0), min(x + 1, size - 1) + 1))
                     for x, y, z in self.coords]

        # distance[a][b]: king steps from a to b on an empty board (sideways/diagonal in the
        # layer, plus one step per layer)
        self.distance = [[max(abs(ax - bx), abs(ay - by)) + abs(az - bz) for bx, by, bz in self.coords]
                         for ax, ay, az in self.coords]
        self.max_distance = (size - 1) + (z_max - z_min)

        self.features = None    # per piece and square, what the scoring looks at (ai.evaluate)
        self.scoring_cache = {}  # value tables for each set of scoring parameters
