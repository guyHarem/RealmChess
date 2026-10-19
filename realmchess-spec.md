# RealmChess Game Specification & Architecture Plan

## 1. Overview
**RealmChess** is a 3-dimensional chess variant played across 5 parallel layers of $8 \times 8$ grids. The game introduces verticality, environmental obstacles (rocks in the Dungeon layers), and highly agile vertical skirmishers (Knights).

### The Board Coordinate System ($X, Y, Z$)
Every position on the board is represented as a 3D tuple: `(x, y, z)` where:
*   **$X$ (File/Column):** `0` to `7` (corresponding to columns A to H).
*   **$Y$ (Rank/Row):** `0` to `7` (corresponding to ranks 1 to 8).
*   **$Z$ (Layer/Altitude):** `-2` to `+2`.
    *   `+2`: **Space** (Top Layer)
    *   `+1`: **Sky** (Upper Layer)
    *   `0`: **Ground** (Standard Chess Board; the kings, queens, rooks, pawns and one pair of knights and bishops start here)
    *   `-1`: **Dungeon** (Lower Layer, contains static rocks)
    *   `-2`: **Abyss** (Bottom Layer, contains static rocks)

### Starting position
The Ground holds the ordinary chess starting position. Each player also has two **Knights in the
Dungeon** (under the b and g files of their back rank) and two **Bishops in the Sky** (above the
c and f files), and two **Pawns in Space** and two **Pawns in the Abyss** (on the b and g files
of their pawn rank, clear of the Abyss rocks), so 24 pieces a side.

### Square colors
The checkered pattern shifts by one square on every other layer: a cell is dark when
$x + y + z$ is even. A Bishop therefore stays on one color wherever it goes, and a Rook stepping
up or down changes color just as it does stepping sideways.

---

## 2. Core Physics: The "Two-Axis" Rule
To prevent cognitive overload and maintain strategic playability, **no piece can simultaneously move along more than two axes at once.**

*   **Allowed Movements:** Change 1 axis (e.g., $X$ only) or change 2 axes by equal steps (e.g., $X$ and $Y$, or $Y$ and $Z$).
*   **Forbidden Movements:** No piece can change $X$, $Y$, and $Z$ at the same time (no "tri-diagonal" or corner-to-corner 3D movements like Forward-Left-Up).

---

## 3. Piece Movement & Capture Rules

### The King
*   **Movement:** Standard chess King movements on its current plane ($XY$ movements), **plus** the ability to move exactly 1 step straight up or down ($Z \pm 1$).
*   **Diagonals:** The King **cannot step** diagonally across layers (no vertical-diagonal moves).
*   **Captures:** The King **can capture** there. An enemy piece standing one square sideways, forward or back and one layer up or down can be taken, like any piece next to it on its own layer. A Queen or Bishop gives check from such a square, so without this the King could be checked by a piece beside it that it could not touch. It follows that the King guards those squares: the two Kings may not stand there next to each other, and a piece there is protected by its King.
*   **Total Moves in Open Space:** 10 potential squares (8 on its current layer, 1 directly above, 1 directly below).

### The Rook (1-Axis Piece)
*   **Movement:** Can move any number of squares along a **single** axis.
*   *Planar:* Changes only $X$ or only $Y$ (orthogonal movement on its current layer).
*   *Vertical:* Changes only $Z$ (acts as an "elevator" straight up or down through layers on the same square).

### The Bishop (2-Axis Piece)
*   **Movement:** Can move any number of squares by changing exactly **two** axes by equal amounts.
*   *Planar Diagonal:* Changes $X$ and $Y$ equally (traditional chess diagonal).
*   *Vertical-Longitudinal Diagonal:* Changes $Y$ and $Z$ equally (e.g., Forward-Up or Backward-Down).
*   *Vertical-Latitudinal Diagonal:* Changes $X$ and $Z$ equally (e.g., Left-Up or Right-Down).
*   **Restriction:** Cannot change all three axes (no Forward-Left-Up).

### The Queen (1-Axis or 2-Axis Piece)
*   **Movement:** Combines the movements of the Rook and Bishop.
*   **Obstacles:** Like the Rook and Bishop, she is completely blocked by physical obstacles (other pieces and Dungeon rocks) and cannot jump over them.

### The Knight (3D L-Shape / 2-Axis Piece)
*   **Movement:** Moves 2 steps on one axis and 1 step on another axis.
*   *Planar L-move:* 2 steps $X$, 1 step $Y$ (or vice versa) on the same layer.
*   *3D L-move:* 2 steps planar, 1 step $Z$ (layer) OR 1 step planar, 2 steps $Z$.
*   **Jumping:** The Knight can jump over any pieces and the static **rocks** in the Dungeon.

### The Pawn
*   **Standard Move:** Moves 1 step forward on its current plane `(y + 1)` OR climbs/descends 1 layer forward `(y + 1, z ± 1)`.
*   **Double-Move:** From its starting rank, a Pawn can advance 2 squares forward on its plane, OR it can advance 2 squares forward while climbing/descending exactly 2 layers `(y + 2, z ± 2)`. The square it passes over must be empty.
*   **Capture:** Captures diagonally forward on its current plane `(x ± 1, y + 1)` OR diagonally forward while changing one layer `(x ± 1, y + 1, z ± 1)`. This is the only exception to the Two-Axis rule. A straight-ahead climb `(y + 1, z ± 1)` is a move, never a capture.
*   **En Passant:** Allowed on both planar double-moves and vertical-diagonal double-moves. The capturing pawn lands on the square the enemy pawn passed over.
*   **Promotion:** A Pawn promotes to a Queen, Rook, Bishop, or Knight when it reaches the opponent's final rank (`y = 7` for White, `y = 0` for Black) on **any** of the 5 layers.

---

## 4. Dungeon Obstacles (Layers -1 and -2)
To reward Knights and create a vertical layout of "chokepoints" and "safe havens," we place static, symmetrical **rocks** in the Dungeon.

### Layer -1: The "Hourglass" Symmetrical Layout (8 Rocks)
Rocks are placed in the central columns and intermediate ranks to block straight vertical drops.
*   **Rock Coordinates (x, y, -1):**
    *   `(2, 2, -1)` [C3] and `(5, 2, -1)` [F3]
    *   `(3, 3, -1)` [D4] and `(4, 3, -1)` [E4]
    *   `(3, 4, -1)` [D5] and `(4, 4, -1)` [E5]
    *   `(2, 5, -1)` [C6] and `(5, 5, -1)` [F6]

### Layer -2: The "Cross" Symmetrical Layout (8 Rocks)
Rocks are offset to create a vertical "zig-zag" effect, meaning a piece cannot drop straight down through both layers in these columns, but can slide in diagonally.
*   **Rock Coordinates (x, y, -2):**
    *   `(3, 2, -2)` [D3] and `(4, 2, -2)` [E3]
    *   `(2, 3, -2)` [C4] and `(5, 3, -2)` [F4]
    *   `(2, 4, -2)` [C5] and `(5, 4, -2)` [F5]
    *   `(3, 5, -2)` [D6] and `(4, 5, -2)` [E6]

---

## 5. Software Architecture (Python)
The codebase must enforce a **strict separation of concerns** between the Game Logic (Core Engine) and the Graphical User Interface (UI).

```text
realmchess/
│
├── engine/                  # Pure Python Game Logic (Zero GUI dependencies)
│   ├── __init__.py
│   ├── board.py             # Coordinate dictionary, pieces, and rock placements
│   ├── pieces.py            # Movement and capture math for each piece type
│   └── game_state.py        # Turn state, check/checkmate detection, promotions
│
└── ui/                      # Visual Presentation Layer (e.g., Pygame / Godot)
    ├── __init__.py
    └── main.py              # Visual rendering, input handling, and Engine API calls
```

### State Representation
The board state should be stored in a **Sparse Map (Python Dictionary)** where the keys are `(x, y, z)` tuples and values are instances of `Piece` or `Rock` classes.
```python
# Conceptual board state lookup
self.board_state = {
    (4, 0, 0): King(color="white"),
    (2, 2, -1): Rock(), # Static obstacle
}
```

### The 3 Core Engine API Calls
The UI must interact with the Core Engine *only* through these three primary functions:

1.  **`get_board_state() -> dict`**
    *   *Description:* Returns the current state of the board.
    *   *Returns:* A dictionary mapping `(x, y, z)` to the occupying item (Piece type, color, or Rock).

2.  **`get_legal_moves(coord: tuple) -> list[tuple]`**
    *   *Description:* Calculates all valid destination coordinates for the piece currently sitting at the given `(x, y, z)` coordinate.
    *   *Returns:* A list of validated `(x, y, z)` coordinate tuples.

3.  **`make_move(from_coord: tuple, to_coord: tuple) -> dict`**
    *   *Description:* Attempts to execute a move from one coordinate to another. It handles turn validation, captures, checks/checkmates, promotions, and en passant.
    *   *Returns:* A status dictionary containing:
        *   `success` (bool): True if the move was legal and executed.
        *   `check` (bool): True if the opponent's king is now in check.
        *   `game_over` (bool): True if checkmate or stalemate was reached.
        *   `promotion_required` (bool): True if a pawn reached the back rank and a piece choice is pending.
