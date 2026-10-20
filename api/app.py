"""
Flask API for RealmChess game engine.
Provides HTTP endpoints for game management.
"""

import json
import mimetypes
import os
import sys

# Make the project root importable so `python api/app.py` works from any directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from api import handoff
from api.handoff import Arrival, key as handoff_key, key_matches
from api.limits import Limiter, Slots
from api.rooms import Rooms
from api.utils import convert_response
from engine.pieces import Queen, Rook, Bishop, Knight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
mimetypes.add_type("application/manifest+json", ".webmanifest")   # not every system knows it

# Two modes. On your own machine (the default) everything is open: the developer test bench,
# the shared "main" room, position editing, requests from the Vite dev server. Hosted for
# real visitors (REALMCHESS_ENV=production, see serve.py) those are closed and limits apply.
PRODUCTION = os.environ.get("REALMCHESS_ENV") == "production"

app = Flask(__name__, static_folder=None)
app.config.update(
    PRODUCTION=PRODUCTION,
    MAX_CONTENT_LENGTH=64 * 1024,                                    # no request needs more
    DIST=os.path.join(ROOT, "realmchess-frontend", "dist"),            # the built pages (npm run build)
)
if not PRODUCTION:
    CORS(app)   # the dev pages come from another port; hosted, pages and API share one address
else:
    # Hosting providers put proxies in front. Each adds the address it heard from to the end
    # of X-Forwarded-For, so with N proxies the visitor is the Nth entry from the end;
    # anything before that was sent by the visitor and proves nothing. N differs per host
    # (Render: 2, see render.yaml). /api/health shows the address this arrives at.
    PROXIES = int(os.environ.get("REALMCHESS_TRUST_PROXY", "1"))
    if PROXIES > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=PROXIES)

# Per visitor, hosted mode only
limits = {
    "requests": Limiter(600, 60),      # everything: a page asks about once a second per open game
    "new_games": Limiter(20, 60),
    "computer_moves": Limiter(40, 60),
    "thinking": Slots(2),              # computer moves being thought about at the same time
}


def hosted():
    return app.config["PRODUCTION"]


def visitor():
    return request.remote_addr or "unknown"


def too_many():
    return jsonify({"success": False, "slow_down": True,
                    "error": "Too many requests. Wait a moment and try again."}), 429

# Every game lives in its own room (api/rooms.py), chosen with ?game=<room id>. POST /api/games
# opens a new one. Two rooms always exist for the developer test bench and the tests:
# "main" (used when a request names no game) and "practice".
rooms = Rooms()
game_manager = rooms.get("main").manager
practice_manager = rooms.get("practice").manager


# Games handed over by the previous server on a deploy (api/handoff.py)
arrival = Arrival()


@app.before_request
def choose_game():
    if not request.path.startswith('/api/'):
        return None   # a page or one of its files
    if request.path == '/api/handoff':
        return None   # the previous server, which has its own key
    if hosted() and not limits["requests"].allow(visitor()):
        return too_many()
    if request.path in ('/api/games', '/api/health'):
        return None
    room_id = request.args.get("game", "main")
    room = rooms.get(room_id)
    if room is None:
        arrival.wait()   # just after a deploy, the game may still be on its way here
        room = rooms.get(room_id)
    if room is None or (hosted() and room.permanent):
        return jsonify({"success": False, "gone": True, "error": "This game no longer exists"}), 404
    g.room = room
    g.manager = room.manager
    # The secret key a seated player sends with every request; None for anyone else
    g.seat = room.seat_of(request.headers.get("X-Seat"))
    g.color = g.seat[:5] if g.seat else None
    room.seen(g.seat)
    return None


def reply(response, **extra):
    """Send a game-manager answer to the page, with the room's details added"""
    room = g.room
    status_code = 200 if response.get("success") else 400
    response = convert_response(response)
    response.update(extra)
    if "board" in response:
        response["game_id"] = room.id
        response["kind"] = room.kind
        response["stamp"] = room.stamp()
        response["online"] = room.describe(g.seat) if room.kind == "online" else None
        # A team game: whose turn it is within the team to move ("white2": White's second player)
        response["teams"] = {"turn": room.turn_seat()} if room.teams else None
    return jsonify(response), status_code


def refuse(message, status_code=400):
    return jsonify({"success": False, "error": message}), status_code


def online():
    return g.room.kind == "online"


def not_online():
    return refuse("That is not available in an online game") if online() else None


def parse_coord(value):
    """Convert a JSON [x,y,z] list to an (x,y,z) tuple, or raise ValueError"""
    if (not isinstance(value, list) or len(value) != 3 or
            not all(type(n) is int for n in value)):
        raise ValueError("Coordinate must be [x, y, z] integers")
    return tuple(value)


# ==================== GAME SETUP ====================

def start(manager, data):
    """Begin a game in a room from the options the page sent"""
    response = manager.new_game(rocks=bool(data.get("rocks", True)), move_limit=data.get("move_limit", 50),
                                clock=data.get("clock"), computer=data.get("computer"), portals=data.get("portals"))
    if response.get("success") and response.get("computer") and hasattr(manager._think, "warm_up"):
        manager._think.warm_up()
    return response


@app.route('/api/games', methods=['POST'])
def open_game():
    """Open a new room and start a game in it. Body: {"kind": "local" | "computer" | "online" | "practice"}
    plus the options of /api/game/new. An online game also takes "side": the color the
    creator plays ("white" by default); the answer then carries the creator's secret "seat" key.
    "teams": true makes it a team game: two players a side taking turns with the army (on one
    screen, against the computer, or online, where a team may also play the computer).
    The answer's "game_id" is the room: pass it as ?game=<game_id> from then on."""
    if hosted() and not limits["new_games"].allow(visitor()):
        return too_many()
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "local")
    side = data.get("side", "white")
    if kind == "online" and side not in ("white", "black"):
        return refuse('side must be "white" or "black"')
    if kind == "computer" and data.get("computer") is None:
        return refuse("A computer game needs the computer's color and level")
    if data.get("computer") is not None and not (kind == "computer" or (kind == "online" and data.get("teams"))):
        return refuse("Only a computer game, or a team playing the computer online, takes a computer")
    if kind == "practice" and data.get("teams"):
        return refuse("Practice boards have no teams")
    if kind == "online" and data.get("computer") is not None and data["computer"].get("color") == side:
        return refuse("The computer plays the other side")
    try:
        room = rooms.create(kind)
    except ValueError as e:
        return refuse(str(e))
    room.teams = bool(data.get("teams"))
    g.room, g.manager, g.seat, g.color = room, room.manager, None, None
    response = start(room.manager, data)
    if not response.get("success"):
        return reply(response)
    if kind == "online":
        seat = room.sit(side)
        g.seat, g.color = side, side
        return reply(response, seat=seat)
    return reply(response)


@app.route('/api/game/new', methods=['POST'])
def new_game():
    """Start a new game in the same room. Optional body:
    {"rocks": true, "move_limit": 50, "clock": {"initial": 600, "increment": 5},
     "computer": {"color": "black", "level": "hard"}} (clock in seconds; omit clock or computer for none)"""
    return not_online() or reply(start(g.manager, request.get_json(silent=True) or {}))


@app.route('/api/game/join', methods=['POST'])
def join_game():
    """Open an online game's link: take a free seat if there is one, on the side given as
    {"side": "white" | "black"} if any. The answer carries "seat" (your secret key) when you
    are a player; without it you are watching."""
    if not online():
        return refuse("Only online games are joined")
    side = (request.get_json(silent=True) or {}).get("side")
    if side not in (None, "white", "black"):
        return refuse('side must be "white" or "black"')
    seat, g.seat = g.room.join(request.headers.get("X-Seat"), side)
    g.color = g.seat[:5] if g.seat else None
    g.room.seen(g.seat)
    return reply(g.manager.get_state(), seat=seat)


# ==================== QUERIES ====================

@app.route('/api/game/state', methods=['GET'])
def get_state():
    """Get current game state (board, player, status). A page that asks every second adds
    ?since=<the "stamp" of its last answer>: if nothing has changed it gets a short answer
    with just the clock and who is connected."""
    response = g.manager.get_state()
    if request.args.get("since") == g.room.stamp():
        return jsonify({"success": True, "unchanged": True, "stamp": g.room.stamp(), "clock": response["clock"],
                        "online": g.room.describe(g.seat) if online() else None,
                        "teams": {"turn": g.room.turn_seat()} if g.room.teams else None})
    return reply(response)


@app.route('/api/game/legal-moves', methods=['GET'])
def get_legal_moves():
    """Get legal moves for a piece at given coordinate"""
    # Extract coordinate from query string: ?from=[0,1,0]
    from_str = request.args.get('from')
    
    if not from_str:
        return jsonify({"success": False, "error": "Missing 'from' parameter"}), 400
    
    try:
        # Parse JSON array string to list, then to tuple: "[0,1,0]" → (0,1,0)
        from_coord = parse_coord(json.loads(from_str))
        
        return reply(g.manager.get_legal_moves(from_coord))
    except ValueError:
        return jsonify({"success": False, "error": "Invalid coordinate format"}), 400


# ==================== MOVES ====================

@app.route('/api/game/move', methods=['POST'])
def make_move():
    """Execute a move"""
    data = request.get_json(silent=True)
    
    if not data or 'from' not in data or 'to' not in data:
        return jsonify({"success": False, "error": "Missing 'from' or 'to' in body"}), 400
    
    try:
        # Convert lists to tuples
        from_coord = parse_coord(data['from'])
        to_coord = parse_coord(data['to'])
        
        with g.manager.lock:
            refusal = not_your_move()
            if refusal:
                return refusal
            response = g.manager.make_move(from_coord, to_coord)
            if response.get("success"):
                g.room.clear_offer()   # moving on answers a pending offer with "no"
            return reply(response)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid coordinate format"}), 400


def not_your_move():
    """In an online game only the player whose turn it is may move"""
    if not online():
        return None
    if g.color is None:
        return refuse("You are watching this game", 403)
    if g.color != g.manager.game.current_player:
        return refuse("It is not your move", 403)
    if g.seat != g.room.turn_seat():
        return refuse("It is your teammate's move", 403)
    return None


@app.route('/api/game/computer-move', methods=['POST'])
def computer_move():
    """Let the computer think and play. The page calls this when it is the computer's turn.
    When every thinker is taken the answer has "busy": true and the page asks again."""
    if not hosted():
        return reply(g.manager.computer_move())
    who = visitor()
    if not limits["computer_moves"].allow(who) or not limits["thinking"].take(who):
        return too_many()
    try:
        return reply(g.manager.computer_move())
    finally:
        limits["thinking"].give_back(who)


@app.route('/api/game/say', methods=['POST'])
def say():
    """Online team games: {"text": "...", "move": {"from": [x,y,z], "to": [x,y,z]} (optional)}
    to your teammate. A move is a suggestion for the position now; it is not played."""
    if not online():
        return refuse("Only online team games have team messages")
    data = request.get_json(silent=True) or {}
    move = data.get("move")
    try:
        if move is not None:
            if not isinstance(move, dict):
                raise ValueError('move must be {"from": [x, y, z], "to": [x, y, z]}')
            move = {"from": parse_coord(move.get("from")), "to": parse_coord(move.get("to"))}
        g.room.say(g.seat, data.get("text", ""), move)
    except ValueError as e:
        return refuse(str(e))
    return reply(g.manager.get_state())


@app.route('/api/game/hint', methods=['POST'])
def hint():
    """The computer suggests a move for the player to move, without playing it. Not between
    people online (that would be help from outside the game); a team playing the computer may."""
    if online() and g.manager.computer is None:
        return refuse("Hints are only for games against the computer or on one screen")
    if online() and g.color is None:
        return refuse("You are watching this game", 403)
    if g.room.kind == "practice":
        return refuse("The lessons and puzzles have their own help")
    if not hosted():
        return reply(g.manager.hint())
    who = visitor()
    if not limits["computer_moves"].allow(who) or not limits["thinking"].take(who):
        return too_many()
    try:
        return reply(g.manager.hint())
    finally:
        limits["thinking"].give_back(who)


# ==================== SPECIAL MOVES ====================

@app.route('/api/game/promote', methods=['POST'])
def promote_pawn():
    """Promote a pawn to a new piece"""
    data = request.get_json(silent=True)
    
    if not data or 'coord' not in data or 'piece_type' not in data:
        return jsonify({"success": False, "error": "Missing 'coord' or 'piece_type' in body"}), 400
    
    try:
        coord = parse_coord(data['coord'])
        piece_type_str = data['piece_type']  # e.g., "Queen", "Rook", etc.
        
        # Map string to piece class
        piece_classes = {
            'Queen': Queen,
            'Rook': Rook,
            'Bishop': Bishop,
            'Knight': Knight
        }
        
        if piece_type_str not in piece_classes:
            return jsonify({"success": False, "error": f"Invalid piece type: {piece_type_str}"}), 400
        
        # Get piece class and create instance with current player's color
        PieceClass = piece_classes[piece_type_str]
        # The turn only passes once the promotion is done, so it's the current player's piece
        with g.manager.lock:
            refusal = not_your_move()
            if refusal:
                return refusal
            new_piece = PieceClass(g.manager.game.current_player)
            return reply(g.manager.promote_pawn(coord, new_piece))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid coordinate format"}), 400


# ==================== ENDING THE GAME BY CHOICE ====================

@app.route('/api/game/resign', methods=['POST'])
def resign():
    """Resign. Optional body: {"color": "white"}; without it the player to move resigns.
    In an online game you resign for yourself, whatever the body says."""
    data = request.get_json(silent=True) or {}
    if online():
        if g.color is None:
            return refuse("You are watching this game", 403)
        response = g.manager.resign(g.color)
        if response.get("success"):
            g.room.clear_offer()
        return reply(response)
    return reply(g.manager.resign(data.get("color")))


@app.route('/api/game/draw', methods=['POST'])
def agree_draw():
    """Both players agreed to a draw (two players on one screen), or a draw offer to the
    computer. Online games use /api/game/offer."""
    return not_online() or reply(g.manager.agree_draw())


# ==================== OFFERS BETWEEN ONLINE PLAYERS ====================

def offer_reply(action):
    if not online():
        return refuse("Only online games have offers")
    try:
        action()
    except ValueError as e:
        response = g.manager.get_state()
        response["success"] = False
        response["error"] = str(e)
        return reply(response)
    return reply(g.manager.get_state())


@app.route('/api/game/offer', methods=['POST'])
def make_offer():
    """Offer a draw or ask to take your last move back: {"kind": "draw" | "takeback"}.
    The opponent sees it in the game's "online" details and answers with /api/game/answer."""
    data = request.get_json(silent=True) or {}
    return offer_reply(lambda: g.room.make_offer(g.color, data.get("kind")))


@app.route('/api/game/answer', methods=['POST'])
def answer_offer():
    """Answer the pending offer: {"accept": true | false}. The player who made the offer can
    withdraw it with {"accept": false}."""
    data = request.get_json(silent=True) or {}
    return offer_reply(lambda: g.room.answer(g.color, bool(data.get("accept"))))


# ==================== UNDO ====================

@app.route('/api/game/undo', methods=['POST'])
def undo_move():
    """Undo the last move. Online games ask the opponent instead (/api/game/offer)."""
    return not_online() or reply(g.manager.undo_move())


# ==================== SANDBOX (TESTING ONLY) ====================
# Position editing for the test bench frontend. Not part of the game API.

def sandbox_response(response):
    return reply(response)


@app.before_request
def no_sandbox_online():
    """Positions cannot be edited in a game between two remote players. Hosted, only the
    scratch boards of the lessons and puzzles can be edited at all."""
    if request.path.startswith('/api/debug/'):
        if online():
            return refuse("That is not available in an online game")
        if hosted() and g.room.kind != "practice":
            return refuse("That is not available here")
    return None


# ==================== HANDOVER ON A DEPLOY ====================

@app.route('/api/handoff', methods=['GET', 'POST'])
def handoff_games():
    """Between the old and the new server on a deploy (see api/handoff.py); needs the shared
    key. GET: the new server asks for every game. POST {"rooms": [...], "done": true on the
    last batch}: the old server sends them as it stops. Either answer names this server, so a
    server that has reached itself can tell."""
    if not key_matches(request.headers.get("X-Handoff-Key")):
        return refuse("No such endpoint", 404)
    if request.method == "GET":
        return jsonify({"success": True, "server": handoff.SERVER, "rooms": handoff.snapshots(rooms, app.logger.warning)})
    if request.headers.get("X-Handoff-From") == handoff.SERVER:
        return jsonify({"success": True, "server": handoff.SERVER, "self": True, "restored": 0})
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("rooms"), list):
        return refuse("Expected {\"rooms\": [...]}")
    restored = arrival.take(rooms, data, how="pushed", log=app.logger.warning)
    return jsonify({"success": True, "server": handoff.SERVER, "restored": restored})


# ==================== THE PAGES ====================

@app.route('/api/health')
def health():
    """For a hosting provider to check that the server is up. Hosted, it also says which
    address it takes the caller for: that is how to check REALMCHESS_TRUST_PROXY on a new
    host, since the limits per visitor go by this address. And whether REALMCHESS_HANDOFF_KEY
    is set, without which a deploy ends the games in progress."""
    if hosted():
        # "handoff": whether this server has the key to take over games on a deploy (not the
        # key), and how many games it took over from the previous server
        return jsonify({"success": True, "visitor": visitor(), "handoff": handoff_key() is not None,
                        "taken_over": dict(arrival.counts)})
    return jsonify({"success": True})


@app.route('/', defaults={"path": "index.html"})
@app.route('/<path:path>')
def pages(path):
    """The built frontend (realmchess-frontend/dist), so one program serves pages and API.
    In development the pages come from the Vite dev server instead."""
    if path.startswith('api/'):
        return refuse("No such endpoint", 404)
    dist = app.config["DIST"]
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return refuse("The pages are not built. Run: npm --prefix realmchess-frontend run build", 404)
    response = send_from_directory(dist, path)
    if path.startswith('assets/'):
        # Built files carry a fingerprint in their name, so they never change
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.route('/api/debug/setup', methods=['POST'])
def debug_setup():
    """Replace the whole position: {"pieces": [{"coord", "type", "color"}], "current_player", "rocks",
    "size", "z_min", "z_max", "portals"}. The board defaults to the full 8, -2, 2; lessons use
    5, -1, 1. portals: pairs of cells, [[[x,y,z], [x,y,z]], ...]."""
    data = request.get_json(silent=True) or {}
    try:
        pieces = [{"coord": parse_coord(item["coord"]), "type": item["type"], "color": item.get("color")}
                  for item in data.get("pieces", [])]
    except (TypeError, KeyError, ValueError, AttributeError):
        return jsonify({"success": False, "error": "Invalid pieces list"}), 400
    
    return sandbox_response(g.manager.setup_position(
        pieces, data.get("current_player", "white"), bool(data.get("rocks", True)),
        size=data.get("size", 8), z_min=data.get("z_min", -2), z_max=data.get("z_max", 2),
        portals=data.get("portals")))


@app.route('/api/debug/place', methods=['POST'])
def debug_place():
    """Put a piece on a square (replacing whatever is there): {"coord", "type", "color"}"""
    data = request.get_json(silent=True) or {}
    try:
        coord = parse_coord(data.get("coord"))
    except ValueError:
        return jsonify({"success": False, "error": "Invalid coordinate format"}), 400
    
    return sandbox_response(g.manager.place_piece(coord, data.get("type"), data.get("color")))


@app.route('/api/debug/remove', methods=['POST'])
def debug_remove():
    """Empty a square: {"coord"}"""
    data = request.get_json(silent=True) or {}
    try:
        coord = parse_coord(data.get("coord"))
    except ValueError:
        return jsonify({"success": False, "error": "Invalid coordinate format"}), 400
    
    return sandbox_response(g.manager.remove_piece(coord))


@app.route('/api/debug/turn', methods=['POST'])
def debug_turn():
    """Choose who moves next: {"player"}"""
    data = request.get_json(silent=True) or {}
    return sandbox_response(g.manager.set_turn(data.get("player")))


@app.route('/api/debug/rocks', methods=['POST'])
def debug_rocks():
    """Add or remove the dungeon rocks: {"enabled"}"""
    data = request.get_json(silent=True) or {}
    return sandbox_response(g.manager.set_rocks(bool(data.get("enabled"))))


# ==================== SERVER ====================

if __name__ == '__main__':
    # Development only: this server reloads on every change and shows a debugger in the
    # browser, which must never face the internet. To host the game, run serve.py instead.
    if PRODUCTION:
        raise SystemExit("api/app.py is the development server. For hosting run: python serve.py")
    # The computer player thinks in a worker process so the server stays responsive
    from api.thinker import ProcessThinker
    rooms.set_thinker(ProcessThinker())
    # macOS reserves port 5000 for AirPlay Receiver, so default to 5001
    app.run(debug=True, port=int(os.environ.get("PORT", 5001)))
