"""
Scoring a position for the computer player, in hundredths of a pawn.

The score is material plus a value for where each piece stands. FastBoard keeps it up to
date on every move, so reading it costs nothing.

Every number that goes into it is a named parameter in DEFAULT_PARAMS. Each piece on each
square has a list of features (how many squares it reaches from there, how far it is from
the Ground, how far a pawn has advanced...), and its value is the sum of feature x parameter.
That makes the numbers tunable: tools/tune.py plays the computer against itself and fits
the parameters to who won.
"""
from ai.tables import PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, ROCK, BLACK

# Tuned by self-play (tools/tune.py), 2,000 games a round. Each round had to win a 300-game
# match before it was kept. Three rounds under the first rules (228-23, 253-196 over 600
# games, 160-73), one after the king's capture rule and the extra knights and bishops came in
# (130-93 with 77 draws), and one after the pawns in Space and the Abyss (151-92 with 57
# draws; it also mates a bare king in 78 of 128 test endgames against 65).
# The starting guesses came from how many squares each piece reaches on an empty board
# compared with ordinary chess; FIRST_GUESSES keeps them.
DEFAULT_PARAMS = {
    # What a piece is worth (the pawn is the fixed yardstick)
    "pawn": 100, "knight": 314, "bishop": 367, "rook": 427, "queen": 1217,
    # ... plus this much for each square it could reach, above its average. (A rook reaches
    # the same number of squares from everywhere, so it has no such term.)
    "reach_knight": 8.63, "reach_bishop": 1.6, "reach_queen": -4.21,
    # ... plus this much for each layer it stands away from the Ground
    "layer_knight": 8.22, "layer_bishop": -13.57, "layer_rook": -9.07, "layer_queen": -7.64,
    # A pawn that has advanced 1, 2, ... ranks (5 = one step from promotion on the full board)
    "pawn_advance_1": 21, "pawn_advance_2": 25, "pawn_advance_3": 121, "pawn_advance_4": 270, "pawn_advance_5": 389,
    "pawn_central": 1.25,    # scales the bonus for central pawns stepping forward
    "pawn_layer": 13.07,     # per layer away from the Ground, until the pawn is far advanced
    # King: per rank it has left its back rank (up to 4), and per layer away from the Ground
    "king_rank": -7.77, "king_layer": -7.32,
    # ... and per square it could step to from where it stands (4 in a corner of the top or
    # bottom layer, 10 in the open)
    "king_freedom": 1.2,
    # Closing in on the enemy king: per step of closeness (3 next to it, 2, 1, then nothing).
    # The rook's is below zero: holding it at zero mated a bare king a little more often but
    # won fewer full games (55% against 60% over 300).
    "near_pawn": 21.0, "near_knight": 28.0, "near_bishop": 18.19, "near_rook": -16.9, "near_queen": 33.0,
    # Cornering a bare king: per exit square it has lost, and per step our king is closer to
    # it. Set with tools/endgames.py; such endings are too rare in self-play to fit.
    "corner_exits": 70.0, "corner_kings": 35.0,
}
FIRST_GUESSES = {
    "pawn": 100, "knight": 480, "bishop": 500, "rook": 540, "queen": 1150,
    "reach_knight": 2.0, "reach_bishop": 1.5, "reach_queen": 0.5,
    "layer_knight": 0.0, "layer_bishop": 0.0, "layer_rook": 0.0, "layer_queen": 0.0,
    "pawn_advance_1": 2, "pawn_advance_2": 5, "pawn_advance_3": 10, "pawn_advance_4": 22, "pawn_advance_5": 45,
    "pawn_central": 1.0, "pawn_layer": -3.0,
    "king_rank": -12.0, "king_layer": 0.0,
    "king_freedom": 0.0,
    "near_pawn": 0.0, "near_knight": 0.0, "near_bishop": 0.0, "near_rook": 0.0, "near_queen": 0.0,
    "corner_exits": 0.0, "corner_kings": 0.0,
}
FIXED_PARAMS = ("pawn",)     # never tuned: everything else is measured against it
PARAM_NAMES = tuple(DEFAULT_PARAMS)

NAME_OF_PIECE = {PAWN: "pawn", KNIGHT: "knight", BISHOP: "bishop", ROOK: "rook", QUEEN: "queen"}
VALUES = {piece: DEFAULT_PARAMS[name] for piece, name in NAME_OF_PIECE.items()}
VALUES[KING] = 0

MATE = 100_000       # scores at or beyond MATE - 1000 mean a forced mate
DRAW = 0


def piece_features(tables):
    """features[piece][square] = {parameter name: amount} for a WHITE piece on that square.
    Built once per board size."""
    if getattr(tables, "features", None) is not None:
        return tables.features
    size, n = tables.size, tables.n
    features = {piece: [dict() for _ in range(n)] for piece in (PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING)}

    for piece in (KNIGHT, BISHOP, ROOK, QUEEN):
        name = NAME_OF_PIECE[piece]
        if piece == KNIGHT:
            reach = [len(tables.knight[square]) for square in range(n)]
        else:
            reach = [sum(len(line) for line in tables.slides[piece][square]) for square in range(n)]
        average = sum(reach) / n
        for square, (x, y, z) in enumerate(tables.coords):
            entry = {name: 1, f"layer_{name}": abs(z)}
            if piece != ROOK:
                entry[f"reach_{name}"] = reach[square] - average
            features[piece][square] = entry

    middle = (size - 1) / 2
    for square, (x, y, z) in enumerate(tables.coords):
        advanced = max(0, y - 1)
        central = middle - abs(x - middle)
        pawn = {"pawn": 1, "pawn_central": central * (2 + 2 * min(advanced, 3))}
        if advanced:
            pawn[f"pawn_advance_{min(advanced, 5)}"] = 1
        if advanced <= 3:
            pawn["pawn_layer"] = abs(z)
        features[PAWN][square] = pawn
        features[KING][square] = {"king_rank": min(y, 4), "king_layer": abs(z),
                                  "king_freedom": len(tables.king[square])}

    tables.features = features
    return features


def build_piece_square_values(tables, params=None):
    """pst[piece code][square]: what the piece is worth on that square. White's values are
    positive and Black's negative, so the sum over the board is White's lead."""
    params = params or DEFAULT_PARAMS
    features = piece_features(tables)
    size, n = tables.size, tables.n
    pst = [[0] * n for _ in range(16)]
    for piece, per_square in features.items():
        white = [round(sum(params[name] * amount for name, amount in per_square[square].items()))
                 for square in range(n)]
        for square, (x, y, z) in enumerate(tables.coords):
            pst[piece][square] = white[square]
            # Black sees the board from the other end
            pst[piece | BLACK][square] = -white[tables.index[(x, size - 1 - y, z)]]
    return pst


def closeness(distance):
    """How close a piece is to the enemy king, for the near_* parameters"""
    return max(0, 4 - distance)


def build_near_values(tables, params=None):
    """near[piece code][distance to the enemy king]: the bonus for standing that close.
    White's values are positive and Black's negative, like the piece-square values."""
    params = params or DEFAULT_PARAMS
    near = [[0] * (tables.max_distance + 1) for _ in range(16)]
    for piece, name in NAME_OF_PIECE.items():
        for distance in range(tables.max_distance + 1):
            value = round(params[f"near_{name}"] * closeness(distance))
            near[piece][distance] = value
            near[piece | BLACK][distance] = -value
    return near


def cornering(board):
    """Extra score (White minus Black) when one side has only its king left: the attacker
    gains as the bare king loses exits and as the attacker's own king comes closer."""
    white, black = board.squares
    if len(black) == 1 and len(white) > 1:
        winner, sign = 0, 1
    elif len(white) == 1 and len(black) > 1:
        winner, sign = 1, -1
    else:
        return 0
    own, bare = board.kings[winner], board.kings[winner ^ 1]
    if own < 0 or bare < 0 or board.insufficient(winner):
        return 0
    tables = board.t
    cells = board.cells
    # Exits are counted from the shape of the board and the rocks only. Counting just the
    # squares the attacker does not cover was tried: no better at mating, and much slower.
    exits = 0
    for square in tables.king[bare]:
        if cells[square] != ROCK:
            exits += 1
    return sign * (board.corner_exits * (10 - exits)
                   + board.corner_kings * (tables.max_distance - tables.distance[own][bare]))


def position_features(board):
    """{parameter name: White's amount minus Black's} for a whole position. With the
    parameters, this gives board.score plus cornering(board) (up to rounding); the tuner
    works on these."""
    tables = board.t
    features = piece_features(tables)
    size = tables.size
    total = dict.fromkeys(PARAM_NAMES, 0.0)
    for colour, sign in ((0, 1), (1, -1)):
        enemy_king = board.kings[colour ^ 1]
        for square in board.squares[colour]:
            piece = board.cells[square] & 7
            if enemy_king >= 0 and piece != KING:
                total[f"near_{NAME_OF_PIECE[piece]}"] += sign * closeness(tables.distance[enemy_king][square])
            if colour:
                x, y, z = tables.coords[square]
                square = tables.index[(x, size - 1 - y, z)]
            for name, amount in features[piece][square].items():
                total[name] += sign * amount
    # The cornering term, split into its two parts
    saved = board.corner_exits, board.corner_kings
    board.corner_exits, board.corner_kings = 1, 0
    total["corner_exits"] = float(cornering(board))
    board.corner_exits, board.corner_kings = 0, 1
    total["corner_kings"] = float(cornering(board))
    board.corner_exits, board.corner_kings = saved
    return total


def evaluate(board):
    """The position's score for the player to move"""
    white, black = board.squares
    # Only tiny positions can be dead draws, so the check is skipped for all the others
    if len(white) + len(black) <= 4 and board.insufficient(0) and board.insufficient(1):
        return DRAW
    score = board.score
    if len(white) == 1 or len(black) == 1:
        score += cornering(board)
    return score if board.side == 0 else -score
