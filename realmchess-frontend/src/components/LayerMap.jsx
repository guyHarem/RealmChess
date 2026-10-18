// The current layer flattened and seen from above, with 2D pieces. Clicking a square
// does the same thing as clicking the cell on the 3D board.
import { isDarkSquare, keyOf, layerOf, parsePiece, sameCoord } from '../lib/chess.js'
import PieceIcon from './PieceIcon.jsx'

const FILES = 'abcdefgh'

export default function LayerMap({ board, size, z, side, selected, legalMoves, goal, lastMove, showMoves = true, onCellClick }) {
  const layer = layerOf(z)
  const range = [...Array(size).keys()]
  // White at the bottom when white sits nearest, otherwise the view is turned round
  const ranks = side === 'black' ? range : [...range].reverse()
  const files = side === 'black' ? [...range].reverse() : range

  return (
    <div className="map-frame">
      <div className="map-ranks" aria-hidden="true">
        {ranks.map((y) => (
          <span key={y}>{y + 1}</span>
        ))}
      </div>
      <div className="layer-map" style={{ gridTemplateColumns: `repeat(${size}, minmax(0, 1fr))` }}>
        {ranks.map((y) =>
          files.map((x) => {
            const coord = [x, y, z]
            const piece = parsePiece(board[keyOf(coord)])
            const legal = legalMoves.some((move) => sameCoord(move, coord))
            const classes = ['map-cell']
            if (sameCoord(selected, coord)) classes.push('is-selected')
            if (legal && piece) classes.push('is-capture')
            if (sameCoord(goal, coord)) classes.push('is-goal')
            if (sameCoord(lastMove?.from, coord)) classes.push('is-left')
            if (sameCoord(lastMove?.to, coord)) classes.push('is-arrived')
            return (
              <button
                key={`${x}-${y}`}
                type="button"
                className={classes.join(' ')}
                style={{ backgroundColor: isDarkSquare(x, y, z) ? layer.dark : layer.light }}
                aria-label={`${FILES[x]}${y + 1} on ${layer.name}${piece ? `, ${piece.color ?? ''} ${piece.type}` : ''}`}
                onClick={() => onCellClick(coord)}
              >
                {piece?.type === 'Rock' && <span className="map-rock" />}
                {piece && piece.type !== 'Rock' && <PieceIcon type={piece.type} color={piece.color} size={26} />}
                {legal && !piece && showMoves && <span className="map-dot" />}
              </button>
            )
          }),
        )}
      </div>
      <div className="map-files" aria-hidden="true">
        {files.map((x) => (
          <span key={x}>{FILES[x]}</span>
        ))}
      </div>
    </div>
  )
}
