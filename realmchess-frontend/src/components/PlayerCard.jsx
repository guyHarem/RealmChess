import PieceIcon from './PieceIcon.jsx'
import { otherColor } from '../lib/chess.js'

// `points` is the value of the pieces this player has captured; `lead` is how far ahead that puts them
// `compact` is the one-line strip used on a phone
export default function PlayerCard({ color, name, toMove, points, lead, captured, note, clock, compact = false }) {
  if (compact) {
    return (
      <section className={`player is-compact ${toMove ? 'is-to-move' : ''}`}>
        <span className="player-name">
          <i className={`chip chip-${color}`} />
          {color === 'white' ? 'White' : 'Black'}
        </span>
        <span className="player-note">{note ?? (toMove ? 'Your move' : name)}</span>
        <span className="player-material" aria-label={`Captured material worth ${points}`}>
          {lead > 0 && <span className="lead">+{lead}</span>}
          <strong>{points}</strong>
        </span>
        {clock}
      </section>
    )
  }
  return (
    <section className={`player ${toMove ? 'is-to-move' : ''}`}>
      <div className="player-top">
        <span className="player-name">
          <i className={`chip chip-${color}`} />
          {color === 'white' ? 'White' : 'Black'}
        </span>
        {clock}
      </div>
      <div className="player-note">{note ?? (toMove ? 'Your move' : name)}</div>
      <div className="player-row">
        <span>Material</span>
        <span className="player-material">
          {lead > 0 && <span className="lead">+{lead}</span>}
          <strong>{points}</strong>
        </span>
      </div>
      <div className="player-row">
        <span>Captured</span>
        <span className="player-captured">
          {captured.length === 0 && <span className="player-none">none</span>}
          {captured.map((type, i) => (
            <PieceIcon key={i} type={type} color={otherColor(color)} size={24} />
          ))}
        </span>
      </div>
    </section>
  )
}
