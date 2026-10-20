"""
Anonymous play counts and the players' feedback, for the admin page.

Counts are kept per day: games started (by kind and options), games finished (how, and who
won), pages visited, hints, messages, lobby games. Visitors are counted once a day each,
without keeping their address: the server keeps a short hash of the address and the day,
salted with a secret, so the same visitor on another day cannot be linked. Nothing goes to
any other service, and no cookie is set.

Like the games, this lives in the server's memory. A deploy hands it to the new server with
the games (api/handoff.py); a crash loses it.
"""
import hashlib
import hmac
import secrets
import threading
import time
from collections import Counter
from datetime import datetime, timezone

DAYS_KEPT = 180
VISITORS_PER_DAY = 50000       # distinct visitors remembered for a day; beyond that, not counted
FEEDBACK_KEPT = 500
FEEDBACK_KINDS = ("bug", "idea", "other")
FEEDBACK_LENGTH = 2000
# Pages and events a page may report (POST /api/visit)
PAGES = ("home", "setup", "game", "learn", "scenarios", "lobby")
EVENTS = ("lesson_done", "puzzle_solved", "lobby_join", "quick_play")


def today(now=None):
    return datetime.fromtimestamp(now if now is not None else time.time(), timezone.utc).strftime("%Y-%m-%d")


class Stats:
    """Counters per day. A new server takes over the old one's counts on a deploy: those it
    was handed are kept apart from its own, so taking a newer copy again never counts twice."""

    def __init__(self, salt=None, now=time.time):
        self._now = now
        self._lock = threading.Lock()
        self._salt = salt or secrets.token_bytes(16)
        self._own = {}          # day -> Counter, counted here
        self._inherited = {}    # day -> Counter, handed over by the previous server
        self._visitors = {}     # day -> set of short hashes (today and yesterday only)

    def set_salt(self, secret):
        """Share the visitor hashing with the next server, so a deploy does not count everyone
        twice (the handoff key is shared by both)"""
        if secret:
            self._salt = hashlib.sha256(b"realmchess-visitors" + secret.encode()).digest()

    def count(self, name, n=1):
        with self._lock:
            self._own.setdefault(today(self._now()), Counter())[name] += n

    def visitor(self, address):
        """Count this address once a day"""
        day = today(self._now())
        tag = hmac.new(self._salt, f"{day}|{address}".encode(), hashlib.sha256).hexdigest()[:12]
        with self._lock:
            seen = self._visitors.setdefault(day, set())
            if tag in seen or len(seen) >= VISITORS_PER_DAY:
                return
            seen.add(tag)
            for old in [each for each in self._visitors if each < day and each != self._yesterday(day)]:
                del self._visitors[old]

    @staticmethod
    def _yesterday(day):
        stamp = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
        return today(stamp - 86400)

    def days(self):
        """{day: {name: count}}, newest last, with "visitors" for each day"""
        with self._lock:
            merged = {}
            for layer in (self._inherited, self._own):
                for day, counts in layer.items():
                    merged.setdefault(day, Counter()).update(counts)
            for day, seen in self._visitors.items():
                merged.setdefault(day, Counter())["visitors"] = len(seen)
            cutoff = today(self._now() - DAYS_KEPT * 86400)
            return {day: dict(merged[day]) for day in sorted(merged) if day >= cutoff}

    # ---- handing over on a deploy ----

    def snapshot(self):
        days = self.days()
        with self._lock:
            visitors = {day: sorted(seen) for day, seen in self._visitors.items()}
        # Visitor counts travel as the hashes for the days still being counted
        for day in visitors:
            days.get(day, {}).pop("visitors", None)
        return {"days": days, "visitors": visitors}

    def take(self, data):
        """The previous server's counts (all of them, as it last had them)"""
        if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
            raise ValueError("Expected {\"days\": {...}}")
        inherited = {}
        for day, counts in data["days"].items():
            if isinstance(day, str) and isinstance(counts, dict):
                inherited[day] = Counter({str(name): int(n) for name, n in counts.items()
                                          if isinstance(n, int) and n >= 0})
        with self._lock:
            self._inherited = inherited
            for day, tags in (data.get("visitors") or {}).items():
                if isinstance(tags, list):
                    seen = self._visitors.setdefault(day, set())
                    seen.update(str(tag)[:12] for tag in tags[:VISITORS_PER_DAY - len(seen)])


class Inbox:
    """What players sent with the Feedback button, newest last"""

    def __init__(self, now=time.time):
        self._now = now
        self._lock = threading.Lock()
        self._items = {}   # id -> item

    def add(self, kind, text, contact="", page="", game="", agent=""):
        if kind not in FEEDBACK_KINDS:
            raise ValueError(f"kind must be one of: {', '.join(FEEDBACK_KINDS)}")
        text = str(text or "").strip()[:FEEDBACK_LENGTH]
        if not text:
            raise ValueError("Write something first")
        item = {"id": secrets.token_hex(6), "at": round(self._now()), "kind": kind, "text": text,
                "contact": str(contact or "").strip()[:200], "page": str(page or "")[:100],
                "game": str(game or "")[:16], "agent": str(agent or "")[:200], "done": False}
        with self._lock:
            self._items[item["id"]] = item
            self._trim()
        return item

    def _trim(self):
        """Keep the newest FEEDBACK_KEPT, dropping handled ones first"""
        extra = len(self._items) - FEEDBACK_KEPT
        if extra > 0:
            oldest = sorted(self._items.values(), key=lambda item: (not item["done"], item["at"]))
            for item in oldest[:extra]:
                del self._items[item["id"]]

    def mark(self, item_id, done):
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                raise ValueError("No such message")
            item["done"] = bool(done)

    def items(self):
        with self._lock:
            return sorted((dict(item) for item in self._items.values()), key=lambda item: item["at"])

    def snapshot(self):
        return self.items()

    def take(self, items):
        """The previous server's messages: added to these; one marked handled on either stays so"""
        if not isinstance(items, list):
            raise ValueError("Expected a list of messages")
        with self._lock:
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                here = self._items.get(item["id"])
                if here is not None:
                    here["done"] = here["done"] or bool(item.get("done"))
                    continue
                self._items[item["id"]] = {
                    "id": item["id"][:16], "at": int(item.get("at", 0)), "kind": item.get("kind", "other"),
                    "text": str(item.get("text", ""))[:FEEDBACK_LENGTH], "contact": str(item.get("contact", ""))[:200],
                    "page": str(item.get("page", ""))[:100], "game": str(item.get("game", ""))[:16],
                    "agent": str(item.get("agent", ""))[:200], "done": bool(item.get("done"))}
            self._trim()


def game_started(stats, room, data):
    """Count a new game by its kind and options"""
    options = room.manager.options or {}
    kind = "open" if room.public else room.kind
    stats.count("games.started")
    stats.count(f"games.kind.{kind}")
    if room.teams:
        stats.count("games.teams")
    if room.manager.computer:
        stats.count(f"games.level.{room.manager.computer['level']}")
    if options.get("clock"):
        stats.count("games.clock")
    if not options.get("rocks", True):
        stats.count("games.no_rocks")
    for name in ("portals", "dynamite", "clouds"):
        choice = data.get(name)
        if choice:
            stats.count(f"games.{name}.{choice if choice in ('classic', 'shuffle') else 'set'}")


def game_ended(stats, room, response):
    """Count a finished game once: how it ended, how long it was, and against the computer
    whether the player won"""
    if room.ended or room.kind == "practice" or room.manager.options is None:
        return
    status = response.get("status")
    if status in (None, "ongoing", "check"):
        return
    room.ended = True
    plies = len(response.get("move_history") or [])
    stats.count("games.finished")
    stats.count(f"games.ending.{response.get('draw_reason') or status}")
    stats.count("games.plies", plies)
    computer = room.manager.computer
    winner = response.get("winner")
    if computer:
        result = "drew" if winner is None else "lost" if winner == computer["color"] else "won"
        stats.count(f"computer.{computer['level']}.{result}")
    else:
        stats.count(f"games.winner.{winner or 'draw'}")


def game_forgotten(stats, room):
    """A room swept away after a day: a game nobody finished"""
    if room.kind != "practice" and not room.ended and room.manager.options is not None:
        stats.count("games.abandoned")
