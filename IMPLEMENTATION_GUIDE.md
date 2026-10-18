# RealmChess - Full-Stack Implementation Guide

## Project Overview

**RealmChess** is a 3D chess variant played on a 5-layer 8×8 board (like 5 stacked chess boards).

**Status:** Engine complete ✅ | API/Frontend pending 🔄

**Technology Stack:**
- **Backend:** Python Flask/FastAPI + Chess Engine
- **Frontend:** React/Vue + Three.js (3D rendering)
- **Architecture:** REST API connecting backend engine to frontend UI

---

## Part 1: Engine (COMPLETED ✅)

### Location
- `/Users/guyharem/Projects/RealmChess/engine/`

### Files
- `pieces.py` — All piece movement rules (Pawn, Rook, Knight, Bishop, Queen, King, Rock)
- `board.py` — Board state management (sparse dict storage)
- `game_state.py` — Game orchestration and validation (500+ lines, 27 methods)

### Completed Features
- ✅ All piece movements with 2-axis rule (no piece moves all 3 axes except Pawn captures)
- ✅ Move validation & legal move generation
- ✅ Check/Checkmate/Stalemate detection
- ✅ Castling (kingside & queenside)
- ✅ En Passant (3D-aware)
- ✅ Pawn Promotion
- ✅ Undo Move (with full state restoration)
- ✅ Draw Detection (stalemate + insufficient material)
- ✅ Move History tracking (dict-based)

### Board Layout
```
Coordinates: (X, Y, Z)
X: 0-7 (columns, left to right)
Y: 0-7 (rows, white to black)
Z: -2 to +2 (5 layers: Abyss, Dungeon, Ground, Sky, Space)

White: pieces at Y=0, pawns at Y=1, Z=0
Black: pieces at Y=7, pawns at Y=6, Z=0
```

### Key Classes

**GameState** (main engine)
```python
game = GameState()
game.make_move(from_coord, to_coord)  # Execute move
game.get_legal_moves(from_coord)      # Get valid destinations
game.get_board_state()                # Get board object
game.is_checkmate(color)              # Check end-game
game.is_stalemate(color)              # Check end-game
game.is_draw()                        # Check draw conditions
game.undo_move()                      # Undo last move
game.promote_pawn(coord, new_piece)   # Handle promotion
game.move_history                     # List of moves (dicts)
```

**Board** (low-level operations)
```python
board.get_piece(coord)
board.set_piece(piece, coord)
board.move_piece(from_coord, to_coord)
board.remove_piece(coord)
board.is_coordinate_in_board(coord)
board.board  # dict mapping (x,y,z) → Piece/Rock
```

---

## Part 2: Backend API (PENDING 🔄)

### Goal
Wrap the chess engine in a REST API so frontend can call it via HTTP.

### Framework Choice
- **Recommendation:** Flask (simpler, good for this use case)
- **Alternative:** FastAPI (more modern, auto-documentation)

### File Structure
```
RealmChess/
├── engine/              # (existing)
│   ├── pieces.py
│   ├── board.py
│   └── game_state.py
├── api/                 # NEW - Backend API layer
│   ├── __init__.py
│   ├── app.py           # Flask app + routes
│   ├── game_manager.py  # Manages game instance
│   └── utils.py         # Serialization helpers
├── frontend/            # NEW - React + Three.js
└── requirements.txt     # Python dependencies
```

### API Endpoints (TO IMPLEMENT)

#### Game Management
```
POST   /api/game/new              → Start new game
GET    /api/game/state            → Get current board state
POST   /api/game/move             → Execute move (from, to)
GET    /api/game/legal-moves      → Get legal moves for piece
POST   /api/game/promote          → Promote pawn (coord, piece_type)
POST   /api/game/undo             → Undo last move
GET    /api/game/status           → Get game status (checkmate/stalemate/ongoing)
GET    /api/game/history          → Get move history
```

#### Request/Response Format

**POST /api/game/move**
```json
Request:
{
  "from": [4, 1, 0],
  "to": [4, 3, 0]
}

Response (success):
{
  "success": true,
  "board_state": {...},
  "current_player": "black",
  "move_recorded": true
}

Response (error):
{
  "success": false,
  "error": "Illegal move!"
}
```

**GET /api/game/state**
```json
Response:
{
  "board": {
    "(4,0,0)": {"type": "King", "color": "white"},
    "(3,0,0)": {"type": "Queen", "color": "white"},
    ...
  },
  "current_player": "white",
  "white_king_pos": [4, 0, 0],
  "black_king_pos": [4, 7, 0],
  "is_check": false,
  "is_checkmate": false,
  "is_stalemate": false,
  "is_draw": false
}
```

**GET /api/game/legal-moves?from=[4,1,0]**
```json
Response:
{
  "from": [4, 1, 0],
  "legal_moves": [
    [4, 2, 0],
    [4, 3, 0]
  ]
}
```

### Implementation Steps

1. **Create Flask app structure**
   - Set up routes in `app.py`
   - Create `GameManager` to maintain game instance
   
2. **Implement serialization helpers**
   - Convert Piece objects → JSON
   - Convert board dict → JSON
   - Handle coordinate tuples
   
3. **Add CORS support**
   - Allow frontend to call backend from different port
   
4. **Error handling**
   - Catch engine exceptions
   - Return meaningful error messages
   
5. **Testing**
   - Test each endpoint with curl/Postman first

---

## Part 3: Frontend (PENDING 🔄)

### Goal
Build interactive 3D UI to visualize board and play the game.

### Technology
- **Framework:** React (state management for game)
- **3D Rendering:** Three.js or Babylon.js
- **Styling:** CSS or Tailwind CSS
- **Build Tool:** Vite or Create React App

### Features to Build

#### Board Visualization
- Render 5 layers (user can switch between layers or view all)
- Show all pieces in 3D space
- Color squares/pieces appropriately
- Camera controls (rotate, zoom)

#### Interaction
- Click piece → highlight in one color
- Show legal moves → highlight in different color
- Click destination → execute move
- Display move validation feedback

#### Game UI
- Current player indicator
- Move history (text list)
- Undo button
- Restart button
- Status display (check, checkmate, stalemate, draw)

#### Board Display Options
1. **Single layer view** — See one Z-layer at a time (radio buttons to switch)
2. **Stacked 3D view** — All 5 layers visible with depth
3. **Toggle pieces** — Show/hide certain piece types

### File Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── Board3D.jsx          # Three.js canvas
│   │   ├── GameControls.jsx     # Buttons (undo, restart, etc)
│   │   ├── MoveHistory.jsx      # Display move list
│   │   └── StatusPanel.jsx      # Game status info
│   ├── services/
│   │   └── api.js               # Fetch calls to backend
│   ├── App.jsx                  # Main component
│   └── styles/
│       └── board.css
├── package.json
└── vite.config.js
```

### 3D Rendering Strategy (Three.js example)

```javascript
// Pseudo-code structure
class Board3D {
  constructor() {
    this.scene = new THREE.Scene();
    this.pieces = {}; // Map of coords → mesh objects
    this.squares = {}; // Map of coords → highlight state
  }

  renderBoard() {
    // Create 5 layers of 8x8 squares
    for (let z = -2; z <= 2; z++) {
      for (let x = 0; x < 8; x++) {
        for (let y = 0; y < 8; y++) {
          // Create square geometry
          // Apply color based on checkered pattern
        }
      }
    }
  }

  renderPieces(boardState) {
    // For each (x, y, z) → piece:
    // Load 3D model (or colored cube)
    // Position in 3D space
  }

  highlightLegalMoves(moves) {
    // Highlight each destination square in yellow/green
  }

  onSquareClick(x, y, z) {
    // Send move to backend API
    // Update board display
  }
}
```

### Key Implementation Details

1. **Coordinate mapping**
   - Engine coords: (X, Y, Z) where X,Y = 0-7, Z = -2 to 2
   - 3D world: Scale appropriately so all layers visible
   - Piece size, square size, layer spacing need design

2. **Move flow**
   - User clicks piece A → store selection
   - User clicks piece B → call `POST /api/game/move`
   - Get response → update board
   - Render new positions

3. **State management**
   - Keep game state in React (fetched from backend)
   - Local selection state (which piece selected)
   - Update after each move via API

4. **Layer visualization**
   - Option: Dropdown to switch layers (simpler)
   - Option: See all 5 layers stacked with transparency (cooler)

---

## Part 4: Implementation Checklist

### Phase 1: Backend API Setup (1-2 days)
- [ ] Set up Flask project structure
- [ ] Create GameManager class to manage game instance
- [ ] Implement `/api/game/new` endpoint
- [ ] Implement `/api/game/state` endpoint
- [ ] Implement `/api/game/move` endpoint
- [ ] Add error handling and validation
- [ ] Test with curl/Postman
- [ ] Enable CORS for frontend requests

### Phase 2: Basic Frontend (2-3 days)
- [ ] Set up React project with Vite
- [ ] Install Three.js
- [ ] Create basic 3D board visualization
- [ ] Implement piece rendering
- [ ] Add click-to-select piece functionality
- [ ] Connect to backend API `/api/game/state`
- [ ] Display legal moves on selection

### Phase 3: Move Execution (1-2 days)
- [ ] Implement click-to-move flow
- [ ] Call `/api/game/move` endpoint
- [ ] Update board after move
- [ ] Add move validation feedback
- [ ] Handle errors gracefully

### Phase 4: Game Controls (1 day)
- [ ] Add undo button → call `/api/game/undo`
- [ ] Add restart button → call `/api/game/new`
- [ ] Display game status (check, checkmate, etc)
- [ ] Show move history from API

### Phase 5: Polish (1-2 days)
- [ ] Improve 3D visuals (textures, lighting)
- [ ] Better piece models (or colored cubes)
- [ ] Responsive design
- [ ] Camera controls
- [ ] Layer switching UI

### Phase 6: Bonus Features (Optional)
- [ ] Piece selection animations
- [ ] Move animations
- [ ] Sound effects
- [ ] AI opponent (minimax)
- [ ] Game replay/playback
- [ ] Save/load game

---

## Running the Full Stack

### Terminal 1: Backend
```bash
cd /Users/guyharem/Projects/RealmChess
python3 -m venv venv
source venv/bin/activate
pip install flask flask-cors
python api/app.py  # Runs on http://localhost:5000
```

### Terminal 2: Frontend
```bash
cd /Users/guyharem/Projects/RealmChess/frontend
npm install
npm run dev  # Runs on http://localhost:5173 (Vite default)
```

Then open browser to http://localhost:5173 and play!

---

## Key Design Decisions Made

1. **Engine & API separation** — Engine stays pure Python logic, API just wraps it
2. **REST API** — Simple, easy to debug, good for learning
3. **React + Three.js** — Modern, popular stack for web + 3D
4. **Stateless API** — Each request includes game state (simpler, no server-side session complexity)
5. **5-layer visualization** — Need thoughtful 3D design to not confuse players

---

## Future Enhancements

- [ ] Multiplayer (WebSocket for real-time moves)
- [ ] AI opponent (minimax with alpha-beta pruning)
- [ ] ELO rating system
- [ ] Game database/replay system
- [ ] Mobile support (touch controls)
- [ ] VR support (WebXR)

---

## Quick Reference: Engine API for Frontend Devs

```python
# Initialize
game = GameState()

# Basic operations
game.make_move((4, 1, 0), (4, 3, 0))           # Execute move
game.get_legal_moves((4, 1, 0))                # → [(4,2,0), (4,3,0)]
game.get_board_state().board                   # → {(4,0,0): King(...), ...}

# Game state queries
game.current_player                            # "white" or "black"
game.is_checkmate("white")                     # True/False
game.is_stalemate("black")                     # True/False
game.is_draw()                                 # True/False
game.is_in_check("white")                      # True/False

# History
game.move_history                              # List of move dicts
# Each move dict: {'from': ..., 'to': ..., 'moving_piece': ..., ...}

# Control
game.undo_move()                               # Undo last move
game.promote_pawn((4, 7, 0), Queen("white"))   # Handle promotion
```

---

## Notes for Future Developer

- **Engine is rock-solid** — Don't modify unless debugging
- **API design is flexible** — Can add more endpoints as needed
- **3D visualization is the hard part** — Spend time on camera/controls
- **Test backend with Postman first** — Before connecting frontend
- **Use browser DevTools** — Network tab to debug API calls
- **Move history format:** String like "Pawn(white)" for piece identification

Good luck building! 🚀
