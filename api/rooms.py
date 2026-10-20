"""
Rooms: every game on the server lives in its own room with its own address.

A room is one GameManager plus what an online game needs on top of the rules: who sits on
which side, whether they are still connected, and a pending draw or take-back offer.

There are no accounts. Sitting down gives the browser a secret key for that seat; the
server lets only the holder of White's key move White.

In a team game two players share each army and take turns with it: White's first player
moves, then Black's first, then White's second, Black's second, and round again. Their seats
are "white" and "white2" ("black", "black2"). A side the computer plays has no seats.

An open (public) online game is listed in the lobby, where anyone can take its free seats.
Players there are strangers, so their messages are picked from a short list of phrases.
"""
import secrets
import time

from api.game_manager import GameManager, other

KINDS = ("local", "computer", "online", "practice")
IDLE_SECONDS = 24 * 3600      # a room nobody has touched for this long is removed
MAX_ROOMS = 2000
CONNECTED_SECONDS = 6         # a player heard from this recently counts as connected
OFFERS = ("draw", "takeback")
CHAT_LENGTH = 200             # characters in one message
CHAT_KEPT = 40                # messages kept per game
LOBBY_SECONDS = 15            # an open game leaves the lobby when its players have been gone this long
ABANDON_SECONDS = 60          # gone this long, a player's opponent may claim the game
AWAY_STEP = 10
# What strangers can say to each other in an open game (friends' games take any text)
PHRASES = ("Hello!", "Good luck!", "Have fun!", "Nice move!", "Oops!", "Thanks!", "Well played!",
           "Good game!", "One moment, please.", "Your turn!", "Good idea!", "Watch out!", "I'm not sure.")


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
        self.public = False      # an open game, listed in the lobby for anyone to join
        self.ended = False       # the end of the game has been counted (api/stats.py)
        # Online games: what the players said, oldest first. Each is {"id", "seat", "to": "team"
        # (teammates only) or "all" (both sides), "text", "move": {"from", "to", "piece"} or None,
        # "version": the position it was about}
        self.chat = []
        self._said = 0
        self._now = now
        self.touched = now()
        self.created = self.touched

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

    def gone_for(self, seat):
        """Seconds since this seat's player was last heard from"""
        return self._now() - self.last_seen.get(seat, -1e9)

    def waiting_for_players(self):
        """An online game some of whose seats are still free"""
        return any(seat not in self.seats for seat in self.seat_ids())

    def claimable(self, seat):
        """May this player claim the game because the other side has left? Only once every
        seat is taken, while the game goes on, and when all the other side's players have been
        gone for ABANDON_SECONDS."""
        if seat is None or self.manager._is_over() or self.waiting_for_players():
            return False
        rivals = [each for each in self.seats if each[:5] != seat[:5]]
        return bool(rivals) and all(self.gone_for(each) >= ABANDON_SECONDS for each in rivals)

    def claim(self, seat):
        """Win the game because the other side has left it"""
        with self.manager.lock:
            if seat is None:
                raise ValueError("You are watching this game")
            if not self.claimable(seat):
                raise ValueError("Your opponent has not left the game")
            response = self.manager.abandon(other(seat[:5]))
            if not response["success"]:
                raise ValueError(response["error"])
            self.clear_offer()

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

    # ==================== TALKING ====================

    def say(self, seat, text, move=None, to="team"):
        """A message to your teammate (to="team"), maybe with a move you suggest for the
        position now, or to everyone playing (to="all"). In an open game the text is one of
        PHRASES: the players there are strangers."""
        with self.manager.lock:
            if to not in ("team", "all"):
                raise ValueError('to must be "team" or "all"')
            if to == "team" and not self.teams:
                raise ValueError("Only team games have team messages")
            if seat is None:
                raise ValueError("You are watching this game")
            text = " ".join(str(text or "").split())[:CHAT_LENGTH]
            if text and self.public and text not in PHRASES:
                raise ValueError("In an open game, pick one of the phrases")
            if move is not None and to != "team":
                raise ValueError("Moves are suggested to your teammate only")
            if move is not None:
                game = self.manager.game
                from_coord, to_coord = tuple(move["from"]), tuple(move["to"])
                piece = game.board.get_piece(from_coord)
                if (piece is None or getattr(piece, "color", None) != seat[:5] or
                        game.current_player != seat[:5] or to_coord not in game.get_legal_moves(from_coord)):
                    raise ValueError("That move cannot be played now")
                move = {"from": from_coord, "to": to_coord, "piece": type(piece).__name__}
            if not text and move is None:
                raise ValueError("Say something, or suggest a move")
            self._said += 1
            self.chat.append({"id": self._said, "seat": seat, "to": to, "text": text, "move": move,
                              "version": self.manager._version})
            del self.chat[:-CHAT_KEPT]
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
            # Messages to everyone playing, and your own team's (watchers see none)
            "chat": [dict(message) for message in self.chat
                     if seat and (message.get("to") == "all" or message["seat"][:5] == seat[:5])],
            "public": self.public,
            # In an open game, what the players can say (strangers pick phrases)
            "phrases": list(PHRASES) if self.public else None,
            # Seats whose player has gone, with roughly how long ago (in steps of AWAY_STEP
            # seconds, so the answer does not change every second), and whether the other side
            # has been gone long enough for you to claim the game
            "away": {each: int(min(self.gone_for(each), 3600) // AWAY_STEP * AWAY_STEP) for each in seats
                     if each in self.seats and self.gone_for(each) > CONNECTED_SECONDS},
            "claimable": self.claimable(seat),
        }

    def listing(self):
        """How the lobby shows this open game"""
        options = self.manager.options or {}
        computer = self.manager.computer
        return {
            "id": self.id,
            "teams": self.teams,
            "computer": computer["level"] if computer else None,
            # The seats still free, by side ("white", "black")
            "free": sorted({seat[:5] for seat in self.seat_ids() if seat not in self.seats}),
            "players": len(self.seats),
            "clock": options.get("clock"),
            "rocks": options.get("rocks", True),
            "portals": bool(options.get("portals")),
            "dynamite": bool(options.get("dynamite")),
            "clouds": bool(options.get("clouds")),
            "moves": len(self.manager.game.move_history),
            "waiting": round(self._now() - self.created),
        }


class Rooms:
    def __init__(self, now=time.monotonic):
        self._now = now
        self._rooms = {}
        self.forgotten = None     # called with each room swept away (api/stats.py counts them)
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
            room = self._rooms.pop(room_id)
            if self.forgotten is not None:
                self.forgotten(room)

    def open_games(self):
        """The lobby: open games with a free seat, whose players are still here, oldest first"""
        games = []
        for room in self._rooms.values():
            if (room.kind == "online" and room.public and room.waiting_for_players()
                    and not room.manager._is_over()
                    and any(room.gone_for(seat) <= LOBBY_SECONDS for seat in room.seats)):
                games.append(room)
        return sorted(games, key=lambda room: room.created)

    def live(self):
        """What is going on right now, for the admin page"""
        now = self._now()
        counts = {"rooms": 0, "playing": 0, "online_playing": 0, "players_connected": 0, "open_games": len(self.open_games())}
        for room in self._rooms.values():
            if room.permanent:
                continue
            counts["rooms"] += 1
            recent = now - room.touched <= 60
            waiting = room.kind == "online" and room.waiting_for_players()
            if recent and room.kind != "practice" and not waiting and not room.manager._is_over():
                counts["playing"] += 1
                if room.kind == "online":
                    counts["online_playing"] += 1
            counts["players_connected"] += sum(1 for seat in room.seats if now - room.last_seen.get(seat, -1e9) <= CONNECTED_SECONDS)
        return counts

    def __len__(self):
        return len(self._rooms)
