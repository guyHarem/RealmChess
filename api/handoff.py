"""
Handing the games over when the server is replaced, so a deploy does not end them.

Games live in the server's memory. On a deploy, the host (Render) starts the new server, sends
visitors to it once it answers /api/health, and only then tells the old one to stop
(SIGTERM). The old server then sends every game to the service's public address, which by now
reaches the new server, and the new one carries on with them. It costs nothing, but it only
covers a planned replacement: a crash still loses the games.

A game travels as its starting options and its moves, and the new server replays them, so
nothing but plain JSON crosses over and every move is checked by the rules again. Positions
edited by hand (the lesson and puzzle boards) do not travel; their pages start them afresh.

Settings (environment variables), both needed:
    REALMCHESS_HANDOFF_KEY    a shared secret; the receiving server only takes games with it
    REALMCHESS_HANDOFF_URL    where to send them (default: RENDER_EXTERNAL_URL, set by Render)
"""
import json
import os
import secrets
import threading
import time
import urllib.request

from engine import pieces

BATCH_BYTES = 48 * 1024   # the server refuses requests over 64 KB
PROMOTIONS = ("Queen", "Rook", "Bishop", "Knight")
WAIT_SECONDS = 60         # after starting, how long the new server waits for the old one's games


def key():
    return os.environ.get("REALMCHESS_HANDOFF_KEY") or None


def target():
    return os.environ.get("REALMCHESS_HANDOFF_URL") or os.environ.get("RENDER_EXTERNAL_URL") or None


def key_matches(sent):
    return key() is not None and bool(sent) and secrets.compare_digest(sent, key())


# ==================== ONE GAME, AS JSON ====================

def snapshot(room):
    """A room as plain JSON, or None when it cannot travel (a position edited by hand)"""
    manager = room.manager
    with manager.lock:
        if manager.options is None or room.kind == "practice":
            return None
        game = manager.game
        moves = []
        for entry in game.move_history:
            # A promotion is an entry of its own, after the pawn's move: from and to are the pawn
            promotion = entry.get("promotion_piece") if entry.get("special_move") == "promotion" else None
            moves.append({"from": list(entry["from"]), "to": list(entry["to"]),
                          "promotion": promotion.split("(")[0] if promotion else None,
                          # Notes the game manager adds for move notation, when it has
                          **({"check": entry["check"]} if "check" in entry else {}),
                          **({"ambiguous_from": [list(c) for c in entry["ambiguous_from"]]}
                             if "ambiguous_from" in entry else {})})
        clock = None
        if manager.clock is not None:
            clock = {"white": manager.clock.time_left("white"), "black": manager.clock.time_left("black"),
                     "running": manager.clock.running}
        return {
            "id": room.id,
            "kind": room.kind,
            "seats": dict(room.seats),
            "teams": room.teams,
            "offer": dict(room.offer) if room.offer is not None else None,
            "options": manager.options,
            "moves": moves,
            "clock": clock,
            "clock_stack": [None if entry is None else [dict(entry[0]), entry[1]] for entry in manager._clock_stack],
            "result": dict(manager.result) if manager.result is not None else None,
            "version": manager._version,
            "revision": room.revision,
        }


def restore(rooms, data):
    """Rebuild a room from snapshot(). Raises ValueError when the game does not replay."""
    room = rooms.create(data["kind"], room_id=data["id"])
    try:
        manager = room.manager
        with manager.lock:
            response = manager.new_game(**data["options"])
            if not response["success"]:
                raise ValueError(response["error"])
            game = manager.game
            for move in data["moves"]:
                if move["promotion"]:
                    if move["promotion"] not in PROMOTIONS:
                        raise ValueError(f"Cannot promote to {move['promotion']}")
                    game.promote_pawn(tuple(move["to"]), getattr(pieces, move["promotion"])(game.current_player))
                else:
                    game.make_move(tuple(move["from"]), tuple(move["to"]))
                entry = game.move_history[-1]
                if "check" in move:
                    entry["check"] = move["check"]
                if "ambiguous_from" in move:
                    entry["ambiguous_from"] = [tuple(coord) for coord in move["ambiguous_from"]]
            if manager.clock is not None and data["clock"] is not None:
                # The time the handover took is nobody's: the running clock starts again now
                manager.clock.restore(({"white": data["clock"]["white"], "black": data["clock"]["black"]},
                                       data["clock"]["running"]))
            manager._clock_stack = [None if entry is None else (dict(entry[0]), entry[1]) for entry in data["clock_stack"]]
            manager.result = data["result"]
            manager._version = data["version"] + 1   # pages drop answers older than what they show
            room.seats = dict(data["seats"])
            room.teams = bool(data.get("teams"))
            room.offer = data["offer"]
            room.revision = data["revision"] + 1
            for seat in room.seats:
                room.last_seen[seat] = room.touched
    except Exception:
        rooms.remove(room.id)
        raise
    return room


# ==================== SENDING (the old server) ====================

def send(rooms, url=None, log=print):
    """Send every game to the new server. Returns how many went over."""
    url, secret = url or target(), key()
    if not url or not secret:
        return 0
    batches, batch, size, sent = [], [], 0, 0
    for room in rooms.all():
        data = snapshot(room)
        if data is None:
            continue
        length = len(json.dumps(data))
        if length > BATCH_BYTES:
            log(f"handoff: game {room.id} is too long to send ({length} bytes)")
            continue
        if batch and size + length > BATCH_BYTES:
            batches.append(batch)
            batch, size = [], 0
        batch.append(data)
        size += length
    batches.append(batch)
    for index, batch in enumerate(batches):
        body = json.dumps({"rooms": batch, "done": index == len(batches) - 1}).encode()
        request = urllib.request.Request(url.rstrip("/") + "/api/handoff", data=body, method="POST",
                                         headers={"Content-Type": "application/json", "X-Handoff-Key": secret})
        try:
            with urllib.request.urlopen(request, timeout=10) as answer:
                sent += json.loads(answer.read()).get("restored", 0)
        except OSError as e:
            log(f"handoff: sending failed: {e}")
            return sent
    log(f"handoff: {sent} game(s) sent to the new server")
    return sent


# ==================== RECEIVING (the new server) ====================

class Arrival:
    """The new server's side: whether the old server's games may still be on their way"""

    def __init__(self, now=time.monotonic):
        self._now = now
        self.started = now()
        self.done = threading.Event()

    def expected(self):
        return key() is not None and not self.done.is_set() and self._now() - self.started < WAIT_SECONDS

    def wait(self, longest=15):
        """A page asks for a game this server does not know. It may be one still on its way
        from the old server: give it a moment rather than say it is gone."""
        if self.expected():
            self.done.wait(min(longest, WAIT_SECONDS - (self._now() - self.started)))

    def take(self, rooms, data, log=print):
        restored = 0
        for room in data.get("rooms", []):
            if rooms.get(room.get("id")) is not None:
                continue   # the same id made here meanwhile: keep that one
            try:
                restore(rooms, room)
                restored += 1
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                log(f"handoff: game {room.get('id')} did not replay: {e}")
        if data.get("done"):
            self.done.set()
        return restored
