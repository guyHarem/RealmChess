"""
The three levels of the computer player, and the one function the rest of the program calls.

Weaker levels are weaker because they see less far and choose among several good-looking
moves, not because they play well and then blunder on purpose.

| level  | looks ahead                         | picks                                        |
|--------|-------------------------------------|----------------------------------------------|
| easy   | 1 move, without following captures  | at random among moves within 1.5 pawns       |
| medium | 2 moves, following captures         | at random among moves within 0.3 pawns       |
| hard   | as deep as the time allows          | the best move (some variety in the opening)  |
"""
import random

from ai.board import FastBoard
from ai.search import Search, MATE_BOUND
from engine.board import ARMY_SIZE

LEVELS = {
    "easy": {"depth": 1, "seconds": None, "margin": 150, "quiescence": 0},
    "medium": {"depth": 2, "seconds": None, "margin": 30, "quiescence": 6},
    "hard": {"depth": 64, "seconds": 3.0, "margin": 0, "quiescence": 6},
}
OPENING_PLIES = 8       # hard varies its play this early in the game...
OPENING_MARGIN = 12     # ...among moves this close to the best


class Choice:
    """What the computer decided, in the game manager's terms"""
    def __init__(self, from_coord, to_coord, promotion, result):
        self.from_coord = from_coord
        self.to_coord = to_coord
        self.promotion = promotion      # "Queen", "Rook", "Bishop", "Knight" or None
        self.score = result.score       # for the computer, in hundredths of a pawn
        self.depth = result.depth
        self.nodes = result.nodes
        self.seconds = result.seconds
        self.mate_in = result.mate_in


def think_time(level, clock_left=None, increment=0):
    """Seconds the level may spend: its usual time, or less when its clock is running low"""
    seconds = LEVELS[level]["seconds"]
    if seconds is None or clock_left is None:
        return seconds
    return max(0.05, min(seconds, clock_left / 25 + increment * 0.8))


def choose_move(game, level="hard", seconds=None, rng=None, nodes=None, params=None):
    """Pick a move for the player to move in a GameState. Returns a Choice, or None when
    there is no legal move. seconds overrides the level's own thinking time; params swaps in
    other scoring parameters (used when tuning)."""
    if level not in LEVELS:
        raise ValueError(f"Unknown level: {level}")
    settings = LEVELS[level]
    rng = rng or random
    board = FastBoard.from_game_state(game, params)
    margin = settings["margin"]
    full_armies = len(board.squares[0]) == ARMY_SIZE and len(board.squares[1]) == ARMY_SIZE
    if level == "hard" and full_armies and len(board.history) < OPENING_PLIES:
        margin = OPENING_MARGIN

    search = Search(board, quiescence=settings["quiescence"])
    result = search.run(max_depth=settings["depth"], margin=margin, nodes=nodes,
                        seconds=seconds if seconds is not None else settings["seconds"])
    if result.move is None:
        return None

    move = result.move
    best = max(result.scores.values()) if result.scores else 0
    if margin and result.scores and best < MATE_BOUND:  # a forced mate is always played
        candidates = [(candidate, score) for candidate, score in result.scores.items() if score >= best - margin]
        # Closer to the best is likelier, but anything within the margin can be played
        weights = [1 / (1 + (best - score) / (margin / 3)) for _, score in candidates]
        move = rng.choices([candidate for candidate, _ in candidates], weights)[0]
        result.score = result.scores[move]
    return Choice(*board.describe(move), result)


def accepts_draw(game, computer_color, level="hard"):
    """Would the computer agree to a draw now? Yes when it judges itself clearly worse, or
    when the game is level and has gone on for at least 30 moves each."""
    board = FastBoard.from_game_state(game)
    to_move = "black" if board.side else "white"
    # Looking an odd number of moves ahead flatters the player to move and an even number
    # the other one, so judge by the middle of the two
    score = sum(Search(board).run(max_depth=depth, seconds=0.5).score for depth in (2, 3)) / 2
    if to_move != computer_color:
        score = -score
    return score <= -120 or (abs(score) <= 40 and len(game.move_history) >= 60)
