"""
Rooms: every game on the server lives in its own room with its own address.

A room is one GameManager plus what an online game needs on top of the rules: who sits on
which side, whether they are still connected, and a pending draw or take-back offer.

There are no accounts. Sitting down gives the browser a secret key for that seat; the
server lets only the holder of White's key move White.

In a team game two players share each army and take turns with it: White's first player
moves, then Black's first, then White's second, Black's second, and round again. Their seats
are "white" and "white2" ("black", "black2"). A side the computer plays has no seats.
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
        self.teams = False       # two players a side, taking turns with the army
        self._now = now
        self.touched = now()

    # ==================== SEATS ====================

    def seat_ids(self):
        """Every seat of this game, in the order visitors are given them"""
        computer = self.manager.computer["color"] if self.manager.computer else None
        order = ("white", "black", "white2", "black2") if self.teams else ("white", "black")
        return [seat for seat in order if seat[:5] != computer]

    def seat_of(self, key):
        """The seat this key sits on, or None for a visitor who is only watching"""
        if key:
            for seat, seat_key in self.seats.items():
                if secrets.compare_digest(seat_key, key):
                    return seat
        return None

    def color_of(self, key):
        """The color this key plays, or None for a visitor who is only watching"""
        seat = self.seat_of(key)
        return seat[:5] if seat else None

    def sit(self, seat):
        """Give out the key for a free seat"""
        key = secrets.token_urlsafe(18)
        self.seats[seat] = key
        self.last_seen[seat] = self._now()
        self.revision += 1
        return key

    def join(self, key, side=None):
        """A visitor arrives, wanting to play `side` ("white", "black" or None for any).
        Returns (key, seat): their existing seat, a free one, or (None, None) when there is
        none and they can only watch."""
        with self.manager.lock:
            seat = self.seat_of(key)
            if seat is not None:
                return key, seat
            for seat in self.seat_ids():
                if seat not in self.seats and (side is None or seat[:5] == side):
                    return self.sit(seat), seat
            return None, None

    def turn_seat(self):
        """The seat whose move it is: the color to move, and in a team game which of its two
        players. Each completed turn counts, so taking moves back hands the turn back too."""
        game = self.manager.game
        color = game.current_player
        if not self.teams:
            return color
        turns = len(game._position_keys) - 1
        return color + ("2" if (turns // 2) % 2 else "")

    def seen(self, seat):
        self.touched = self._now()
        if seat is not None:
            self.last_seen[seat] = self.touched

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
            if self.manager.computer is not None:
                return self._ask_the_computer(kind)
            if self.offer is not None and self.offer["kind"] == kind and self.offer["by"] == other(color):
                return self.answer(color, True)
            if kind == "takeback" and self._plies_to_take_back(color) == 0:
                raise ValueError("You have no move to take back")
            self.offer = {"kind": kind, "by": color}
            self.revision += 1

    def _ask_the_computer(self, kind):
        """A team playing the computer online: it answers a draw offer itself, and a take-back
        needs nobody's leave (as on one screen)"""
        if kind == "draw":
            response = self.manager.agree_draw()
            if not response["success"]:
                raise ValueError(response["error"])
        elif not self.manager.undo_move()["success"]:
            raise ValueError("You have no move to take back")
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

    def describe(self, seat):
        """The online part of a game-state reply, for the player (or watcher) asking"""
        now = self._now()
        seats = self.seat_ids()
        return {
            "you": seat[:5] if seat else None,
            "seat": seat,
            "seats": {each: each in self.seats for each in seats},
            "connected": {each: each in self.seats and now - self.last_seen.get(each, -1e9) <= CONNECTED_SECONDS
                          for each in seats},
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
