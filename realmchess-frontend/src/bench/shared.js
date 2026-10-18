// Helpers shared by the 2D and 3D views of the test bench

export const LAYERS = [
  { z: 2, name: 'Space' },
  { z: 1, name: 'Sky' },
  { z: 0, name: 'Ground' },
  { z: -1, name: 'Dungeon' },
  { z: -2, name: 'Abyss' },
]
export const PIECE_TYPES = ['King', 'Queen', 'Rook', 'Bishop', 'Knight', 'Pawn']
export const GLYPHS = { King: '♚', Queen: '♛', Rook: '♜', Bishop: '♝', Knight: '♞', Pawn: '♟' }
export const RANGE = [0, 1, 2, 3, 4, 5, 6, 7]

export const keyOf = (coord) => `[${coord.join(', ')}]`
export const sameCoord = (a, b) => a && b && a[0] === b[0] && a[1] === b[1] && a[2] === b[2]
export const layerLabel = (z) => `z = ${z > 0 ? `+${z}` : z}`

// "Pawn(white)" → { type: "Pawn", color: "white" }, "Rock" → { type: "Rock" }
export function parsePiece(str) {
  if (!str) return null
  const match = str.match(/^(\w+)\((\w+)\)$/)
  return match ? { type: match[1], color: match[2] } : { type: str }
}
