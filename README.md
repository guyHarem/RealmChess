# RealmChess 🎮♟️

A 3D chess variant on five stacked 8×8 boards. This is a **work in progress (WIP)**.

It was called CubeChess until October 2026. Play it at [realmchess.com](https://realmchess.com).

## Project Status: live, still growing

### Phase 1: Backend Engine & API (COMPLETE)
- ✅ **Chess Engine** (`engine/`) — Full 3D chess rules
  - All piece movements (Pawn, Rook, Knight, Bishop, Queen, King)
  - Special moves: Castling, En Passant, Pawn Promotion
  - Check, Checkmate, Stalemate detection
  - Undo/Move history
  - Draw detection (stalemate, threefold repetition, 50-move limit, insufficient material)
  - Any board size from 4×4 to 8×8 with 1 to 5 layers
  
- ✅ **Computer player** (`ai/`) — three levels, see "Computer opponent" below

- ✅ **Flask API** (`api/`) — RESTful backend
  - GameManager wrapper layer
  - Every game in its own room with its own address; online games with seats and offers
  - JSON serialization utilities
  - CORS enabled for frontend

### Phase 2: Frontend UI (COMPLETE)
- ✅ Home page, game setup and the game screen (local two-player)
- ✅ Three.js 3D board: cube-shaped cells, 3D pieces, layer tools, camera controls
- ✅ Move list, captured material, chess clock with increment, undo, resign and draw by agreement
- ✅ Lesson player: ten lessons on a 5×5 board (three layers; the edge-pawn lesson has all five) (`realmchess-frontend/src/lessons.json`)
- ✅ Scenario player: 32 checkmate puzzles in four tiers (`realmchess-frontend/src/scenarios.json`)
- ✅ Play against the computer (easy, medium, hard), with the last move marked on the board
- ✅ Online play with a link: seats without accounts, draw and take-back offers, watching
- ✅ Team games: two players a side take turns with one army, on one screen, against the
  computer, or online (2 against 2, or a team against the computer)
- ✅ Phone layout: the game, lessons and puzzles fit one upright phone screen (3D board on top,
  top view below for tapping, the rest behind a Menu button)
- ✅ Finished lessons, solved puzzles and setup choices are remembered in the browser
- ✅ Sounds for moves, captures, check and the end of a game (with a Sound switch); the piece
  just moved glides to its new cell, a captured piece fades away, and a red pulse marks a king
  in check on the 3D board
- 🔧 Developer test bench at `#/bench` for checking backend behavior

### Phase 3: Polish & Deployment
- ✅ Hosted on Render at realmchess.com; a deploy hands the games in progress to the new server
- ✅ Link previews and home-screen icons (`realmchess-frontend/dev/share-images.html`)
- ✅ Testing suite: engine, computer player, API, online and team play, hosting (`tests/`)
- ⏳ Games that survive a crash (would need storage that outlives the server, which costs extra)

---

## Board Layout

**5 Layers (Z-axis):**
- Z=-2: Abyss (bottom)
- Z=-1: Dungeon
- Z=0: Ground (starting layer)
- Z=1: Sky
- Z=2: Space (top)

**Board Dimensions:** 8×8 per layer (standard chess board per layer)

**Two-Axis Rule:** No piece moves all 3 axes simultaneously (except Pawn captures in 3D context)

**Starting position:** ordinary chess on the Ground, plus two knights each in the Dungeon (under
b and g), two bishops each in the Sky (above c and f), and two pawns each in Space and in the
Abyss (on b and g, the files clear of the Abyss rocks): 24 pieces a side.

**King:** steps like a chess king on its layer, or one cell straight up or down. One cell
sideways together with one layer up or down it cannot step, but it can capture there, so a
queen or bishop cannot check it from the next cell without risk.

**Square colors:** the checkered pattern shifts by one square on every other layer, so a bishop
keeps its color when it changes layer. The top-down view shows chess coordinates (a-h, 1-8).

---

## Setup

### Backend
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Flask server (from the project root)
python api/app.py
# Server runs on http://localhost:5001 (set PORT to change it;
# macOS reserves 5000 for AirPlay Receiver)

# Run the tests
python -m unittest discover -s tests
```

### Frontend
```bash
cd realmchess-frontend
npm install
npm run dev
# App runs on http://localhost:5173 (Vite picks the next free port if that one is taken)
```

### Hosting

Everything above is for your own machine. To run the game for real visitors there is a second
way to start it, which can be tried locally:

```bash
npm --prefix realmchess-frontend run build     # once, and after every change to the pages
venv/bin/python serve.py                       # then open http://localhost:8000
```

`serve.py` runs one program that serves both the built pages and the API, in hosted mode:

- no debugger and no auto-reload (`api/app.py` is the development server and refuses to start
  in hosted mode);
- the shared `main` and `practice` rooms are closed, positions can be edited only on the
  scratch boards of lessons and puzzles, and the developer bench page is not in the build;
- other websites cannot call the API (pages and API share one address, so cross-site access is
  simply off);
- limits per visitor: 600 requests a minute, 20 new games a minute, 40 computer moves a
  minute and 2 being thought about at once. Over a limit the answer is HTTP 429 with
  `slow_down: true`;
- the computer thinks in up to `REALMCHESS_THINKERS` worker processes (one CPU core each;
  default the number of cores minus one, at most 4) with a short line behind them. When the
  line is full a computer move is answered with `busy: true` and the page asks again.

It is a single process on purpose: games live in its memory, and running two copies would
give each its own set of games. When the server is replaced (a deploy), the games carry on
(`api/handoff.py`): the new server, before it answers the health check, asks the old one for
them through the public address `REALMCHESS_HANDOFF_URL` (default `RENDER_EXTERNAL_URL`), and
the old one sends them again as it stops, for the moves made in between, retrying for up to
`REALMCHESS_HANDOFF_PATIENCE` seconds (25) while the address still leads back to itself. Games
travel as starting options plus moves, and the new server replays them. Both need the same secret in `REALMCHESS_HANDOFF_KEY`; without it
nothing is handed over. For its first minute the new server waits briefly before calling an
unknown game gone, in case it is still on its way. A crash still ends the games. Settings are
environment variables: `PORT` (8000), `HOST` (0.0.0.0), `REALMCHESS_THINKERS`, the two above, and
`REALMCHESS_TRUST_PROXY`: how many proxies stand in front of the server (default 1, `0` for
none). Each proxy adds the address it heard from to the end of `X-Forwarded-For`, so the
visitor is that many entries from the end. `GET /api/health` is for a host's health check;
hosted, it answers `{"success": true, "visitor": "<address>", "handoff": true}` with the
address the server takes the caller for, which is how to check the proxy count on a new host,
and whether it has `REALMCHESS_HANDOFF_KEY`.

#### On Render

`render.yaml` describes the whole setup for [Render](https://render.com): one Python web
service that builds the pages and starts `serve.py`.

1. In the Render dashboard choose **New > Blueprint** and pick this repository. Render reads
   `render.yaml` and creates the service (plan `starter`, region Frankfurt; change them in the
   file first if you want others, the region cannot be changed afterwards).
2. When the first deploy is live, open `https://realmchess.onrender.com/api/health`.
   `visitor` must be your own public address. If it is not, the number of proxies in
   `REALMCHESS_TRUST_PROXY` is wrong and the limits per visitor would be shared.
3. Every push to `main` deploys by itself (`autoDeployTrigger: commit`). Render starts the new
   server, moves visitors to it, then stops the old one, which hands its games over. That needs
   `REALMCHESS_HANDOFF_KEY`, which `render.yaml` has Render make up. If the service was created
   before that line existed and the Blueprint does not sync by itself, add the variable in the
   dashboard (**Environment**, any long random value).

The file sets one computer thinker, which suits a plan with one core or less; raise
`REALMCHESS_THINKERS` together with the plan.

#### Custom domain

`render.yaml` attaches realmchess.com to the service; Render adds www.realmchess.com itself,
sends it on to realmchess.com, and issues the HTTPS certificates. At the registrar (GoDaddy),
in the domain's DNS records:

| Type  | Name  | Value                     |
|-------|-------|---------------------------|
| A     | `@`   | `216.24.57.1`             |
| CNAME | `www` | `realmchess.onrender.com` |

Remove any other `A` records for `@` (GoDaddy's parking page), every `AAAA` record, and any
domain forwarding. Then press **Verify** next to each domain in the service's settings on
Render. Until the records have spread, the game is at realmchess.onrender.com.

### Computer opponent

The computer is not trained; it plays like a classic chess program (`ai/`):

1. It copies the position onto a compact board (`ai/board.py`) that lists moves about a
   thousand times faster than the rules engine. `tests/test_fast_board.py` holds the two to
   the same rules move for move.
2. It looks ahead: its moves, your replies, its answers (`ai/search.py`, alpha-beta search).
   Lines that are already worse than one it has found are dropped, and at the end of a line
   it follows captures until the position is quiet.
3. It scores the positions it reaches (`ai/evaluate.py`) by material, by where each piece
   stands, and by how close its pieces are to the enemy king. Against a bare king it also
   scores cornering: the fewer squares that king can step to and the closer the attacker's
   own king, the better. The numbers were tuned by self-play: pawn 1, knight 3.1, bishop 3.7,
   rook 4.3, queen 12.2, and a pawn two steps from promotion is worth about 3.7.

| Level | Looks ahead | Picks |
|---|---|---|
| Easy | 1 move | at random among moves within 1.5 pawns of the best |
| Medium | 2 moves, following captures | at random among moves within 0.3 pawns |
| Hard | as deep as 3 seconds allow (usually 4 to 5 moves) | the best move |

Every scoring number is a named parameter in `ai/evaluate.py`. `python tools/tune.py` tunes
them by self-play in three steps: `games` (the computer plays itself and saves the quiet
positions with each game's result), `fit` (find the parameters whose score best predicts
who won) and `match` (the new numbers play the current ones; keep them only if they win).
Three rounds of 2,000 games have been run. Round one beat the first guesses 228-23 with 49
draws, round two beat round one 253-196 with 151 draws, and round three (with the king terms
added) beat round two 160-73 with 67 draws. A fourth round, after the king's capture rule and
the extra knights and bishops were added, beat the old numbers 130-93 with 77 draws.

`python tools/endgames.py` measures how often the computer mates a bare king from random
positions with a queen, two rooks and so on. Before the cornering terms it managed 11 of 128;
under the current rules it manages 83 of 128. Two rooks, or rook, bishop and knight, still
usually fail.

`python tools/play_match.py` plays the levels against each other (hard beat medium 40-0 and
medium beat easy 20-0), and is the way to check that a change makes the computer stronger.
The server does the thinking in a worker process (`api/thinker.py`).

The scenarios are generated, not hand-written: `python tools/generate_scenarios.py` searches
random positions for ones where White has exactly one way to force mate, and rewrites
`scenarios.json`. `tests/test_scenarios.py` re-checks every puzzle against the engine.

Pages (hash routes): `#/` home, `#/setup` new game, `#/game/<id>` the board, `#/learn` lessons,
`#/scenarios` puzzles, `#/bench` the developer test bench. The frontend needs the backend running; Vite proxies `/api` to port 5001.

The layers are named, top to bottom: Space, Sky, Ground, Dungeon, Abyss. Move notation is
standard chess notation plus a layer mark for moves that land off the Ground:
`↑1` Sky, `↑2` Space, `↓1` Dungeon, `↓2` Abyss (for example `Nb6↑1`).

The test bench edits positions through sandbox endpoints that are for testing only:
`/api/debug/setup`, `/api/debug/place`, `/api/debug/remove`, `/api/debug/turn`, `/api/debug/rocks`.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/games` | POST | Open a room and start a game in it (see Rooms below) |
| `/api/game/join` | POST | Online: take a free seat (optional `{"side"}`), or watch |
| `/api/game/offer` | POST | Online: offer a draw or ask to take a move back |
| `/api/game/answer` | POST | Online: accept, decline or withdraw the offer |
| `/api/game/new` | POST | Start a new game in the same room. Optional body: `{"rocks": true, "move_limit": 50, "clock": {"initial": 600, "increment": 5}, "computer": {"color": "black", "level": "hard"}}` |
| `/api/game/state` | GET | Get current board state |
| `/api/game/move` | POST | Execute a move |
| `/api/game/legal-moves` | GET | Get legal moves for piece |
| `/api/game/computer-move` | POST | The computer thinks and plays (only on its turn) |
| `/api/game/promote` | POST | Promote pawn |
| `/api/game/undo` | POST | Undo last move (also reopens a game ended by resignation, agreement or timeout) |
| `/api/game/resign` | POST | Resign. Optional body: `{"color": "white"}`; default is the player to move |
| `/api/game/draw` | POST | Both players agreed to a draw |

Coordinates are `[x, y, z]` lists. Every game-state response carries `current_player`,
`board` (`{"[4, 0, 0]": "King(white)", ...}`), `status` (`ongoing`, `check`, `checkmate`,
`stalemate`, `draw`, `resigned`, `agreed_draw`, `timeout`), `winner`, `draw_reason`,
`halfmove_clock`, `move_limit`, `clock`, `board_size`, `pending_promotion` and `move_history`. Failed requests return
HTTP 400 with `success: false` and an `error` message.

**Move history:** each entry has `from`, `to`, `moving_piece`, `captured_piece`,
`promotion_piece`, `special_move` (`castling`, `en_passant`, `promotion` or `null`), `check`
(`check`, `checkmate` or `null`) and `ambiguous_from`: the squares of other pieces of the same
kind and color that could legally have made the same move. Move notation uses it to say which
piece moved (as in `Nbd2`).

**Draws:** `draw_reason` is `null` or one of `stalemate`, `repetition` (the same position
occurred three times), `move_limit` (`move_limit` moves by each player, 50 by default, with
no capture and no pawn move; `halfmove_clock` counts the single moves so far) or
`insufficient_material`. A player's material is insufficient when it cannot force checkmate
against a bare king: a lone king, king and one knight, bishop or rook, or king and bishops on
one square color. A bishop's square color counts the layer too (`x + y + z` odd or even), because
a bishop can change layers. The rook is on that list because a king that can step to another
layer always escapes it; on a flat one-layer board a rook is enough. Checkmate positions with a
single piece do exist in corners, but the defender has to walk into them:
`tools/forced_mate.py` solves this exactly on the small board (a rook, bishop or knight wins
only from positions already one move from mate, 0.1% of them; a queen always wins).
The game is drawn when both players are in that state. The draw rules only apply while both kings are on the board, so
practice positions without kings never end in a draw.

**Game over:** once the game has ended (checkmate, any draw, resignation, agreement or
timeout), moving, promoting, resigning and offering a draw are refused with
`"The game is over"`, and `legal-moves` returns an empty list. Undo reopens the game.

**Computer:** `computer` is `null` for two human players, otherwise `{"color", "level"}` with
level `easy`, `medium` or `hard`. The page calls `computer-move` when it is the computer's
turn; the answer is the game after its move plus `thought` (`score`, `depth`, `nodes`,
`seconds`, `mate_in`). `/move` refuses moves for the computer's side. If the game changes
while the computer thinks (undo, new game), its move is dropped and the call fails with
`"The position changed while the computer was thinking"`. Undo takes back the computer's
reply together with your move. `/draw` is an offer the computer may refuse: the call then
fails with `draw_declined: true`. `/resign` without a color is the human's resignation.

**Rooms:** every game lives in its own room (`api/rooms.py`). `POST /api/games` with
`{"kind": "local" | "computer" | "online" | "practice", ...the options of /api/game/new}` opens
one and answers with its `game_id`; every other endpoint then takes `?game=<game_id>`. Game
answers also carry `kind`, `version` and `stamp`. Rooms are kept in memory: handed to the next
server on a deploy, lost in a crash, and removed a day after their last use (a request for one that is gone gets
HTTP 404 with `gone: true`). Two rooms always exist for the test bench and the tests: `main`,
used when no game is named, and `practice`.

**Online games:** opening one with `"side": "white"` answers with a secret `seat` key for that
color. `POST /api/game/join` gives the first other visitor the key for the other color; later
visitors get none and can only watch. The key travels in the `X-Seat` header, and the server
lets only the holder of a color's key move, promote or resign for it. The game's `online`
field tells the page `you` (your color or `null`), which `seats` are taken, who is `connected`
(heard from in the last 6 seconds) and the pending `offer`.
- `POST /api/game/offer` `{"kind": "draw" | "takeback"}` makes an offer; `POST /api/game/answer`
  `{"accept": true | false}` answers it (the offerer can withdraw with `false`). A move declines
  a pending offer. An accepted take-back undoes the asker's last move, and the reply to it if
  there was one.
- `/undo`, `/draw`, `/new` and the sandbox endpoints are refused in online games.

**Team games:** `"teams": true` when opening a game makes it two players a side, taking turns
with one army: White 1, Black 1, White 2, Black 2, and round again (a take-back hands the turn
back too). It works on one screen, against the computer, and online, where the seats are
`white`, `white2`, `black` and `black2`, and a team may also play the computer (open it with
`"kind": "online", "teams": true, "computer": {...}`; that side has no seats, the computer
answers draw offers itself and a take-back needs no leave). `POST /api/game/join` takes
`{"side": "white" | "black"}` to sit on that side; the invite links end in `/<side>`. Every
game answer carries `teams`: `{"turn": "<seat>"}` in a team game, else `null`; online,
`online.seat` is your own seat, and a move out of turn is refused with "It is your teammate's
move". Teammates talk with `POST /api/game/say` `{"text": "...", "move": {"from", "to"}}` (the move
optional, a suggestion that must be playable in the position now); `online.chat` lists your
own team's messages, each with the position `version` it was about.

**Hints:** `POST /api/game/hint` answers with the game and `hint`: `{"from", "to", "promotion",
"version"}`, the computer's choice for the player to move (thinking a second at the strongest
level), not played. For games on one screen, against the computer, and a team playing the
computer online; not between people online.
- Pages keep up by asking `GET /api/game/state?since=<stamp>` once a second; if nothing changed
  the answer is short (`unchanged: true`, the clock and `online`).

To play from another device on your network, start the frontend with `npm run dev -- --host`
and open the address it prints there; the link you send must use that address, not `localhost`.

**Clock:** `clock` is `null` for an untimed game, otherwise
`{"initial", "increment", "white", "black", "running"}` in seconds. A player's clock runs only
on their turn and starts after White's first move; `increment` is added after each timed move.
When the player to move runs out, `status` becomes `timeout` and the opponent is the `winner`.
If that opponent could never checkmate (see below), the game is drawn instead: `winner` is `null` and `draw_reason`
is `timeout_insufficient_material`.
Undo puts the clocks back to where they were before that turn.

**Board size:** the engine works on any board from 4×4 to 8×8 with layers between -2 and 2.
`board_size` is `{"size", "z_min", "z_max"}`. A normal game is always 8, -2, 2; smaller boards
(5, -1, 1 for lessons) start empty and are filled through `/api/debug/setup`, which accepts
`size`, `z_min` and `z_max`.

**Promotion:** when a pawn reaches the last rank, `pending_promotion` holds its coordinate
and the turn does not pass until `/api/game/promote` is called with
`{"coord": [x, y, z], "piece_type": "Queen" | "Rook" | "Bishop" | "Knight"}`.
Undoing a promotion takes back the pawn move as well.

---

## Project Structure

```
RealmChess/
├── engine/                 # Game engine (Python)
│   ├── pieces.py          # Piece classes & movement rules
│   ├── board.py           # Board storage & operations
│   └── game_state.py      # Game logic & validation
├── ai/                    # Computer player
│   ├── tables.py         # Move tables for a board size
│   ├── board.py          # FastBoard: the compact board it thinks on
│   ├── evaluate.py       # Scoring a position
│   ├── search.py         # Looking ahead (alpha-beta)
│   └── levels.py         # Easy, medium, hard
├── api/                   # Flask backend
│   ├── app.py            # HTTP routes
│   ├── game_manager.py   # Business logic wrapper
│   ├── rooms.py          # One room per game; seats and offers for online games
│   ├── clock.py          # Chess clock
│   ├── thinker.py        # Runs the computer's thinking in worker processes
│   ├── limits.py         # Per-visitor limits for the hosted game
│   └── utils.py          # JSON serialization
├── realmchess-frontend/    # React + Vite + Three.js frontend
│   ├── src/
│   │   ├── pages/        # Home, Setup, Game
│   │   ├── components/   # CubeBoard (3D), LayerMap, MoveList, PlayerCard...
│   │   ├── lib/          # API calls, game hook, notation, settings
│   │   ├── bench/        # Developer test bench
│   │   └── pieces3d.js   # Procedural 3D piece models
│   └── dev/              # Sprite renderer used for the design artboards
├── tools/                # Scenario generator, level matches, self-play tuning, endgame and mating-material checks
├── serve.py              # Starts the game in hosted mode (pages + API in one program)
├── tests/                # Test suite
└── IMPLEMENTATION_GUIDE.md # Original planning notes
```

---

## Technologies

- **Backend:** Python 3.x, Flask, Flask-CORS
- **Frontend:** React, Vite, Axios, Three.js (upcoming)
- **Version Control:** Git

---

## Learning Focus

This project is built with a learning-first approach:
- Understanding full-stack architecture
- Backend: Engine → Manager → API layer pattern
- Frontend: Component composition, API integration, 3D rendering
- Proper separation of concerns

---

## Next Steps

1. Re-tune the computer player for the 24-piece start (`tools/tune.py`, self-play); its
   scoring was tuned before the Space and Abyss pawns
2. A way for online teammates to talk (short messages or suggested moves)
3. A lesson on the edge layers: the Space and Abyss pawns, and how pawns change layer
4. The setup page fitting one phone screen, like the other pages
5. Animations for castling (the rook) and for moves taken back
6. Later, once people play: accounts, ratings and finding an opponent; games that survive a
   crash (needs storage that outlives the server, which costs extra on Render)

---

## Notes

See [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) for detailed technical specifications.

---

**Status:** live at realmchess.com. Engine, computer player, pages, online and team play done.
