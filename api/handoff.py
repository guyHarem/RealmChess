"""
Handing the games over when the server is replaced, so a deploy does not end them.

Games live in the server's memory. On a deploy, the host (Render) starts the new server, sends
visitors to it once it answers /api/health, and then tells the old one to stop (SIGTERM).
Both ends hand over, through the service's public address:
  - the new server, while starting and before it answers /api/health, asks for the games
    (GET /api/handoff): the address still leads to the old server then;
  - the old server, as it stops, sends them again (POST /api/handoff) to catch the moves made
    in between. If that reaches the old server itself (the switch can take a moment), it
    tries again.
It costs nothing, but it only covers a planned replacement: a crash still loses the games.

Other things kept in memory (the play counts and the feedback, api/stats.py) travel along:
see keep().

A game travels as its starting options and its moves, and the new server replays them, so
nothing but plain JSON crosses over and every move is checked by the rules again. Positions
edited by hand (the lesson and puzzle boards) do not travel; their pages start them afresh.

Settings (environment variables), the first two needed:
    REALMCHESS_HANDOFF_KEY       a shared secret; a server only hands over games with it
    REALMCHESS_HANDOFF_URL       the public address (default: RENDER_EXTERNAL_URL, set by Render)
    REALMCHESS_HANDOFF_PATIENCE  seconds a stopping server keeps trying to send (default 25;
                                 Render waits 30 before it stops a server by force)
"""
import json
import os
import secrets
import threading
import time
import urllib.request

from engine import pieces

BATCH_BYTES = 48 * 1024   # the server refuses requests over 64 KB (the handoff takes more, see EXTRA_BYTES)
EXTRA_BYTES = 8 * 1024 * 1024   # what a handoff request may carry: the games and keep()'s data
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
            "public": room.public,
            "ended": room.ended,
            "chat": [dict(message, move=None if message["move"] is None else
                          dict(message["move"], **{"from": list(message["move"]["from"]), "to": list(message["move"]["to"])}))
                     for message in room.chat],
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
            room.public = bool(data.get("public"))
            room.ended = bool(data.get("ended"))
            room.chat = [dict(message, move=None if message.get("move") is None else
                              dict(message["move"], **{"from": tuple(message["move"]["from"]),
                                                       "to": tuple(message["move"]["to"])}),
                              version=message["version"] + 1)
                         for message in data.get("chat", [])]
            room._said = max((message["id"] for message in room.chat), default=0)
            room.offer = data["offer"]
            room.revision = data["revision"] + 1
            for seat in room.seats:
                room.last_seen[seat] = room.touched
    except Exception:
        rooms.remove(room.id)
        raise
    return room


# ==================== BETWEEN THE TWO SERVERS ====================

SERVER = secrets.token_hex(8)   # this server process, so a server can tell it has reached itself
EXTRAS = {}                     # name -> (snapshot(), take(data)): handed over besides the games


def keep(name, snapshot_fn, take_fn):
    """Hand this over on a deploy too: snapshot_fn() gives plain JSON, and on the new server
    take_fn(data) takes it in (raising ValueError when it cannot)"""
    EXTRAS[name] = (snapshot_fn, take_fn)


def extras():
    return {name: snapshot_fn() for name, (snapshot_fn, _) in EXTRAS.items()}


def snapshots(rooms, log=print):
    games = []
    for room in rooms.all():
        data = snapshot(room)
        if data is None:
            continue
        length = len(json.dumps(data))
        if length > BATCH_BYTES:
            log(f"handoff: game {room.id} is too long to send ({length} bytes)")
            continue
        games.append(data)
    return games


def _call(url, body=None):
    """GET (body None) or POST to the other server's /api/handoff; returns its JSON answer"""
    request = urllib.request.Request(
        url.rstrip("/") + "/api/handoff", method="GET" if body is None else "POST",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Handoff-Key": key(), "X-Handoff-From": SERVER})
    with urllib.request.urlopen(request, timeout=10) as answer:
        return json.loads(answer.read())


def pull(rooms, arrival, url=None, log=print):
    """The new server, before it takes visitors: ask the old one, which still has them, for
    its games. Returns how many arrived."""
    url = url or target()
    if not url or not key():
        return 0
    try:
        answer = _call(url)
    except (OSError, ValueError) as e:
        log(f"handoff: no games from the previous server ({e})")
        return 0
    if answer.get("server") == SERVER:
        return 0
    taken = arrival.take(rooms, {**{name: answer[name] for name in EXTRAS if name in answer},
                                 "rooms": answer.get("rooms", [])}, how="pulled", log=log)
    log(f"handoff: {taken} game(s) taken over from the previous server")
    return taken


def send(rooms, url=None, log=print, give_up_after=None, pause=1.0):
    """The old server, as it stops: send every game to the new one, which by then has them
    from pull() but not the moves made since. Right after a deploy the public address can
    still lead back here; then try again until it reaches the new server. Returns how many
    games the new server took."""
    url = url or target()
    if not url or not key():
        return 0
    batches, batch, size = [], [], 0
    for data in snapshots(rooms, log):
        length = len(json.dumps(data))
        if batch and size + length > BATCH_BYTES:
            batches.append(batch)
            batch, size = [], 0
        batch.append(data)
        size += length
    batches.append(batch)
    if give_up_after is None:
        give_up_after = float(os.environ.get("REALMCHESS_HANDOFF_PATIENCE", 25))
    deadline = time.monotonic() + give_up_after
    sent = 0
    for index, batch in enumerate(batches):
        while True:
            try:
                body = {"rooms": batch, "done": index == len(batches) - 1}
                if index == 0:
                    body.update(extras())
                answer = _call(url, body)
                if not answer.get("self"):
                    sent += answer.get("restored", 0)
                    break
            except (OSError, ValueError) as e:
                log(f"handoff: sending failed: {e}")
            if time.monotonic() > deadline:
                log(f"handoff: gave up; {sent} game(s) sent")
                return sent
            time.sleep(pause)
    log(f"handoff: {sent} game(s) sent to the new server")
    return sent


# ==================== RECEIVING (the new server) ====================

class Arrival:
    """The new server's side: the games taken over, and whether more may still be on the way"""

    def __init__(self, now=time.monotonic):
        self._now = now
        self.started = now()
        self.done = threading.Event()
        self.counts = {"pulled": 0, "pushed": 0}
        self._taken = {}   # room id -> its version right after it was taken over

    def expected(self):
        return key() is not None and not self.done.is_set() and self._now() - self.started < WAIT_SECONDS

    def wait(self, longest=15):
        """A page asks for a game this server does not know. It may be one still on its way
        from the old server: give it a moment rather than say it is gone."""
        if self.expected():
            self.done.wait(min(longest, WAIT_SECONDS - (self._now() - self.started)))

    def take(self, rooms, data, how="pushed", log=print):
        """Take over games. A game already here is replaced only by a newer copy of one taken
        over earlier and not played on here since (moves made here are the latest)."""
        for name, (_, take_fn) in EXTRAS.items():
            if name in data:
                try:
                    take_fn(data[name])
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    log(f"handoff: {name} not taken over: {e}")
        restored = 0
        for game in data.get("rooms", []):
            room_id = game.get("id")
            here = rooms.get(room_id)
            if here is not None:
                taken = self._taken.get(room_id)
                if taken is None or here.manager._version != taken or game.get("version", -1) + 1 <= taken:
                    continue
                rooms.remove(room_id)
            try:
                room = restore(rooms, game)
                self._taken[room_id] = room.manager._version
                restored += 1
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                log(f"handoff: game {room_id} did not replay: {e}")
                if here is not None:
                    rooms._rooms[room_id] = here   # keep the copy we had
        self.counts[how] += restored
        if data.get("done"):
            self.done.set()
        return restored
