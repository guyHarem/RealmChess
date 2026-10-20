// Score sheet: one row per turn, White then Black. Moves off the Ground carry a layer mark.
import { useEffect, useRef } from 'react'
import { LAYERS, PORTAL_MARK, layerOf, scoreSheet } from '../lib/chess.js'

const portalMark = <span className="moves-portal">{PORTAL_MARK}</span>

function Move({ move }) {
  if (!move) return <span />
  const [before, after] = move.text.split(PORTAL_MARK)
  return (
    <span>
      {after === undefined ? move.text : <>{before}{portalMark}{after}</>}
      {move.mark && <span style={{ color: layerOf(move.z).light }}>{move.mark}</span>}
      {move.suffix}
    </span>
  )
}

export default function MoveList({ history, currentPlayer, finished, portals = false }) {
  const rows = scoreSheet(history)
  const box = useRef(null)

  // Keep the latest move in view
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [history?.length])

  const last = rows[rows.length - 1]
  const whiteToMove = currentPlayer === 'white'

  return (
    <section className="moves">
      <h2>Moves</h2>
      <div className="moves-key">
        {LAYERS.filter((layer) => layer.mark).map((layer) => (
          <span key={layer.z} style={{ color: layer.light }}>
            {layer.mark} {layer.name}
          </span>
        ))}
        {portals && <span>{portalMark} portal</span>}
      </div>
      <div className="moves-box" ref={box}>
        <div className="moves-row moves-head">
          <span />
          <span>
            <i className="chip chip-white" />
            White
          </span>
          <span>
            <i className="chip chip-black" />
            Black
          </span>
        </div>
        {rows.map((row) => (
          <div className="moves-row" key={row.number}>
            <span className="moves-number">{row.number}</span>
            <Move move={row.white} />
            {row.black ? (
              <Move move={row.black} />
            ) : (
              !finished && row === last && !whiteToMove && <span className="moves-next">to move</span>
            )}
          </div>
        ))}
        {!finished && whiteToMove && (
          <div className="moves-row">
            <span className="moves-number">{rows.length + 1}</span>
            <span className="moves-next">to move</span>
            <span />
          </div>
        )}
      </div>
    </section>
  )
}
