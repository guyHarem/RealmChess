// TEMPORARY test bench for checking backend behavior (moves, captures, rocks).
// Not the real game UI: it edits the position through the /api/debug endpoints.
import { useCallback, useEffect, useState } from 'react'
import './bench.css'
import Board3D from './BenchBoard3D.jsx'
import { GLYPHS, LAYERS, PIECE_TYPES, RANGE, keyOf, layerLabel, parsePiece, sameCoord } from './shared.js'


async function api(path, body) {
  const options =
    body === undefined
      ? {}
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  const res = await fetch('/api' + path, options)
  return res.json()
}

function App() {
  const [game, setGame] = useState(null)
  const [selected, setSelected] = useState(null)
  const [legalMoves, setLegalMoves] = useState([])
  const [tool, setTool] = useState('move') // 'move' | 'erase' | { type, color }
  const [freeTurns, setFreeTurns] = useState(true)
  const [view, setView] = useState('3d') // '3d' | '2d'
  const [activeLayer, setActiveLayer] = useState(0) // the plane drawn solid in 3D
  const [error, setError] = useState(null)

  const clearSelection = () => {
    setSelected(null)
    setLegalMoves([])
  }

  // Every state-changing endpoint answers with the full game state
  const apply = useCallback((data) => {
    if (data.board) setGame(data)
    setError(data.success ? null : data.error)
    setSelected(null)
    setLegalMoves([])
    return data
  }, [])

  const call = useCallback(
    async (path, body) => {
      try {
        return apply(await api(path, body))
      } catch {
        setError('Cannot reach the backend. Is `python api/app.py` running on port 5001?')
        return null
      }
    },
    [apply],
  )

  useEffect(() => {
    api('/game/state')
      .then(apply)
      .catch(() => setError('Cannot reach the backend. Is `python api/app.py` running on port 5001?'))
  }, [apply])

  const board = game?.board ?? {}
  const pieceAt = (coord) => parsePiece(board[keyOf(coord)])
  const rocksOn = Object.values(board).includes('Rock')
  const promotion = game?.pending_promotion

  async function selectPiece(coord, piece) {
    let player = game.current_player
    // Test bench convenience: hand the turn to whichever color you click
    if (freeTurns && piece.color !== player && !promotion) {
      const data = await call('/debug/turn', { player: piece.color })
      if (!data?.success) return
      player = piece.color
    }
    try {
      const data = await api('/game/legal-moves?from=' + encodeURIComponent(JSON.stringify(coord)))
      setSelected(coord)
      setLegalMoves(data.legal_moves ?? [])
      setError(data.success ? null : data.error)
    } catch {
      setError('Cannot reach the backend.')
    }
  }

  function onSquareClick(coord) {
    if (!game) return
    const piece = pieceAt(coord)

    if (tool === 'erase') {
      if (piece) call('/debug/remove', { coord })
      return
    }
    if (tool !== 'move') {
      call('/debug/place', { coord, type: tool.type, color: tool.color })
      return
    }

    if (selected && legalMoves.some((move) => sameCoord(move, coord))) {
      call('/game/move', { from: selected, to: coord })
    } else if (piece && piece.type !== 'Rock' && !sameCoord(selected, coord)) {
      selectPiece(coord, piece)
    } else {
      clearSelection()
    }
  }

  const isTool = (type, color) => tool.type === type && tool.color === color
  const captures = legalMoves.filter((move) => pieceAt(move)).length

  return (
    <div className="bench">
      <header>
        <h1>RealmChess test bench</h1>
        <p className="note">Temporary tool for checking backend move and capture behavior.</p>
      </header>

      <section className="panel">
        <div className="group">
          <span className="label">Position</span>
          <button onClick={() => call('/debug/setup', { pieces: [], rocks: rocksOn })}>Empty board</button>
          <button onClick={() => call('/game/new', {})}>Standard start</button>
          <button onClick={() => call('/game/undo', {})}>Undo move</button>
          <label>
            <input
              type="checkbox"
              checked={rocksOn}
              onChange={(e) => call('/debug/rocks', { enabled: e.target.checked })}
            />
            Rocks
          </label>
        </div>

        <div className="group">
          <span className="label">View</span>
          {['3d', '2d'].map((mode) => (
            <button key={mode} className={view === mode ? 'active' : ''} onClick={() => setView(mode)}>
              {mode.toUpperCase()}
            </button>
          ))}
          {view === '3d' && (
            <>
              <span className="label inline">Current plane</span>
              {LAYERS.map(({ z, name }) => (
                <button
                  key={z}
                  title={name}
                  className={activeLayer === z ? 'active' : ''}
                  onClick={() => setActiveLayer(z)}
                >
                  {layerLabel(z)}
                </button>
              ))}
              <span className="note">Drag to rotate, right-drag to pan, scroll to zoom.</span>
            </>
          )}
        </div>

        <div className="group">
          <span className="label">Click does</span>
          <button className={tool === 'move' ? 'active' : ''} onClick={() => setTool('move')}>
            Select / move
          </button>
          <button
            className={tool === 'erase' ? 'active' : ''}
            onClick={() => {
              setTool('erase')
              clearSelection()
            }}
          >
            Erase
          </button>
          {['white', 'black'].map((color) => (
            <span className="palette" key={color}>
              {PIECE_TYPES.map((type) => (
                <button
                  key={type}
                  title={`Place ${color} ${type}`}
                  className={`glyph ${color} ${isTool(type, color) ? 'active' : ''}`}
                  onClick={() => {
                    setTool({ type, color })
                    clearSelection()
                  }}
                >
                  {GLYPHS[type]}
                </button>
              ))}
            </span>
          ))}
        </div>

        <div className="group">
          <span className="label">Turn</span>
          {['white', 'black'].map((color) => (
            <button
              key={color}
              className={game?.current_player === color ? 'active' : ''}
              onClick={() => call('/debug/turn', { player: color })}
            >
              {color}
            </button>
          ))}
          <label title="Clicking a piece of the other color gives that color the turn">
            <input type="checkbox" checked={freeTurns} onChange={(e) => setFreeTurns(e.target.checked)} />
            Any color can move
          </label>
          <span className="status">
            Status: <strong>{game?.status ?? '…'}</strong>
            {game?.draw_reason && game.draw_reason !== 'stalemate' && ` (${game.draw_reason.replace('_', ' ')})`}
          </span>
          <span className="status" title="Moves by each player since the last capture or pawn move">
            Quiet moves: {game ? Math.floor(game.halfmove_clock / 2) : '…'} / {game?.move_limit ?? '…'}
          </span>
          {selected && (
            <span className="status">
              Selected {pieceAt(selected)?.color} {pieceAt(selected)?.type} at {keyOf(selected)}:{' '}
              <strong>{legalMoves.length}</strong> legal moves, <strong>{captures}</strong> captures
            </span>
          )}
        </div>

        {promotion && (
          <div className="group promo">
            <span className="label">Promote pawn at {keyOf(promotion)}</span>
            {['Queen', 'Rook', 'Bishop', 'Knight'].map((type) => (
              <button key={type} onClick={() => call('/game/promote', { coord: promotion, piece_type: type })}>
                {type}
              </button>
            ))}
          </div>
        )}

        {error && <div className="error">{error}</div>}
      </section>

      {view === '3d' && (
        <Board3D
          board={board}
          selected={selected}
          legalMoves={legalMoves}
          activeLayer={activeLayer}
          onSquareClick={onSquareClick}
        />
      )}

      <section className="layers" hidden={view !== '2d'}>
        {LAYERS.map(({ z, name }) => (
          <div className="layer" key={z}>
            <h2>
              {layerLabel(z)} <span>{name}</span>
            </h2>
            <div className="grid">
              {[...RANGE].reverse().map((y) => (
                <div className="row" key={y}>
                  <span className="axis">{y}</span>
                  {RANGE.map((x) => {
                    const coord = [x, y, z]
                    const piece = pieceAt(coord)
                    const isMove = legalMoves.some((move) => sameCoord(move, coord))
                    const classes = [
                      'square',
                      (((x + y + z) % 2) + 2) % 2 === 0 ? 'dark' : 'light',
                      sameCoord(selected, coord) ? 'selected' : '',
                      isMove ? (piece ? 'capture' : 'move') : '',
                    ]
                    return (
                      <button
                        key={x}
                        className={classes.join(' ')}
                        title={`${keyOf(coord)}${board[keyOf(coord)] ? ' ' + board[keyOf(coord)] : ''}`}
                        onClick={() => onSquareClick(coord)}
                      >
                        {piece?.type === 'Rock' && <span className="rock" />}
                        {piece && piece.type !== 'Rock' && (
                          <span className={`glyph ${piece.color}`}>{GLYPHS[piece.type]}</span>
                        )}
                      </button>
                    )
                  })}
                </div>
              ))}
              <div className="row">
                <span className="axis" />
                {RANGE.map((x) => (
                  <span className="axis" key={x}>
                    {x}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </section>

      <section className="history">
        <span className="label">Moves</span>
        {game?.move_history?.length ? (
          <ol>
            {game.move_history.map((move, i) => (
              <li key={i}>
                {move.moving_piece} {keyOf(move.from)} → {keyOf(move.to)}
                {move.captured_piece && ` takes ${move.captured_piece}`}
                {move.promotion_piece && ` becomes ${move.promotion_piece}`}
                {move.special_move && ` (${move.special_move})`}
              </li>
            ))}
          </ol>
        ) : (
          <span className="note"> none yet (editing the position clears the list)</span>
        )}
      </section>
    </div>
  )
}

export default App
