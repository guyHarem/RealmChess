"""
Rooms: every game on the server lives in its own room with its own address.

A room is one GameManager plus what an online game needs on top of the rules: who sits on
which side, whether they are still connected, and a pending draw or take-back offer.

There are no accounts. Sitting down gives the browser a secret key for that color; the
server lets only the holder of White's key move White.
"""
import secrets
import time

from api.game_manager import GameManager, other

KINDS = ("local", "computer", "online", "practice")
IDLE_SECONDS = 24 * 3600      # a room nobody has touched for this long is removed
MAX_ROOMS = 2000
CONNECTED_SECONDS = 6         # a player heard from this recently counts as connected
OFFERS = ("draw", "takeback")


class Room:
    def __init__(self, room_id, kind, manager, now=time.monotonic):
        self.id = room_id
        self.kind = kind
        self.manager = manager
        self.seats = {}          # color -> secret key of the player sitting there (online games)
        self.last_seen = {}      # color -> when that player last asked for the game
        self.offer = None        # {"kind": "draw" or "takeback", "by": color}, or None
        self.revision = 0        # goes up when the seats or the offer change
        self.permanent = False
        self._now = now
        self.touched = now()

    # ==================== SEATS ====================

    def color_of(self, key):
        """The color this key sits on, or None for a visitor who is only watching"""
        if key:
            for color, seat_key in self.seats.items():
                if secrets.compare_digest(seat_key, key):
                    return color
        return None

    def sit(self, color):
        """Give out the key for a free seat"""
        key = secrets.token_urlsafe(18)
        self.seats[color] = key
        self.last_seen[color] = self._now()
        self.revision += 1
        return key

    def join(self, key):
        """A visitor arrives. Returns (key, color): their existing seat, a free one, or
        (None, None) when both seats are taken and they can only watch."""
        with self.manager.lock:
            color = self.color_of(key)
            if color is not None:
                return key, color
            for color in ("white", "black"):
                if color not in self.seats:
                    return self.sit(color), color
            return None, None

    def seen(self, color):
        self.touched = self._now()
        if color is not None:
            self.last_seen[color] = self.touched

    # ==================== OFFERS ====================

    def _plies_to_take_back(self, color):
        """How many single moves a take-back for this player undoes: their last move, and
        the opponent's reply if there has been one. 0 when they have not moved yet."""
        game = self.manager.game
        turns = len(game._position_keys) - 1
        needed = 2 if game.current_player == color else 1
        return needed if turns >= needed else 0

    def make_offer(self, color, kind):
        """Offer a draw or ask to take a move back. Offering what the opponent has just
        offered accepts it."""
        with self.manager.lock:
            if kind not in OFFERS:
                raise ValueError(f"Unknown offer: {kind}")
            if color is None:
                raise ValueError("You are watching this game")
            if self.manager._is_over():
                raise ValueError("The game is over")
            if self.manager.game.pending_promotion is not None:
                raise ValueError("Finish the promotion first")
            if self.offer is not None and self.offer["kind"] == kind and self.offer["by"] == other(color):
                return self.answer(color, True)
            if kind == "takeback" and self._plies_to_take_back(color) == 0:
                raise ValueError("You have no move to take back")
            self.offer = {"kind": kind, "by": color}
            self.revision += 1

    def answer(self, color, accept):
        """Accept or decline the opponent's offer; the player who made it can withdraw it"""
        with self.manager.lock:
            if self.offer is None:
                raise ValueError("There is no offer to answer")
            if color is None:
                raise ValueError("You are watching this game")
            offer = self.offer
            if color == offer["by"]:
                if accept:
                    raise ValueError("Your opponent has to answer that")
            elif accept:
                if offer["kind"] == "draw":
                    response = self.manager.agree_draw()
                    if not response["success"]:
                        raise ValueError(response["error"])
                else:
                    for _ in range(self._plies_to_take_back(offer["by"])):
                        self.manager._undo_one()
            self.offer = None
            self.revision += 1

    def clear_offer(self):
        """A move answers any pending offer with "no" """
        if self.offer is not None:
            self.offer = None
            self.revision += 1

    # ==================== WHAT THE PAGE NEEDS TO KNOW ====================

    def stamp(self):
        """Changes whenever anything a page shows could have changed"""
        return f"{self.manager._version}-{self.revision}"

    def describe(self, color):
        """The online part of a game-state reply, for the player (or watcher) asking"""
        now = self._now()
        return {
            "you": color,
            "seats": {side: side in self.seats for side in ("white", "black")},
            "connected": {side: side in self.seats and now - self.last_seen.get(side, -1e9) <= CONNECTED_SECONDS
                          for side in ("white", "black")},
            "offer": dict(self.offer) if self.offer is not None else None,
        }


class Rooms:
    def __init__(self, now=time.monotonic):
        self._now = now
        self._rooms = {}
        self.thinker = None       # how computer players think (see api/thinker.py); None: inline
        # Two rooms are always there: the developer test bench and the tests use them
        for room_id, kind in (("main", "local"), ("practice", "practice")):
            room = Room(room_id, kind, GameManager(), now)
            room.permanent = True
            self._rooms[room_id] = room

    def get(self, room_id):
        return self._rooms.get(room_id)

    def set_thinker(self, thinker):
        self.thinker = thinker
        for room in self._rooms.values():
            room.manager._think = thinker

    def all(self):
        return list(self._rooms.values())

    def remove(self, room_id):
        self._rooms.pop(room_id, None)

    def create(self, kind, room_id=None):
        """A new room. room_id is only given for a game handed over from the previous server."""
        if kind not in KINDS:
            raise ValueError(f"kind must be one of: {', '.join(KINDS)}")
        self.sweep()
        if len(self._rooms) >= MAX_ROOMS:
            raise ValueError("The server is full. Try again later.")
        if room_id is not None:
            if not isinstance(room_id, str) or not 1 <= len(room_id) <= 16 or room_id in self._rooms:
                raise ValueError("That game id cannot be used")
        else:
            room_id = secrets.token_urlsafe(6)
            while room_id in self._rooms:
                room_id = secrets.token_urlsafe(6)
        manager = GameManager()
        if self.thinker is not None:
            manager._think = self.thinker
        room = self._rooms[room_id] = Room(room_id, kind, manager, self._now)
        return room

    def sweep(self):
        """Forget the rooms nobody has used for a day"""
        cutoff = self._now() - IDLE_SECONDS
        for room_id in [room_id for room_id, room in self._rooms.items()
                        if not room.permanent and room.touched < cutoff]:
            del self._rooms[room_id]

    def __len__(self):
        return len(self._rooms)
