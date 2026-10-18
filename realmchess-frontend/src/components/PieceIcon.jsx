// Flat 2D piece symbols, for the top-down view and the captured-pieces rows.
// (A 3D piece seen from straight above is just a circle.)

const BASE = ' M9 47 h22 a2 2 0 0 1 2 2 v2 a3 3 0 0 1 -3 3 h-20 a3 3 0 0 1 -3 -3 v-2 a2 2 0 0 1 2 -2 z'
const BODY = ' M15.5 28 h9 c0 9 4 11 4.5 19 h-18 c0.5 -8 4.5 -10 4.5 -19 z'
const SHAPES = {
  Pawn: 'M13.5 19 a6.5 6.5 0 1 0 13 0 a6.5 6.5 0 1 0 -13 0 z M14 26 h12 v3 h-12 z M16.5 29 h7 c0 8 4 11 4.5 18 h-16 c0.5 -7 4.5 -10 4.5 -18 z' + BASE,
  Rook: 'M11 9 h4 v3 h3 v-3 h4 v3 h3 v-3 h4 v10 h-18 z M14 19 h12 l1.5 28 h-15 z' + BASE,
  Bishop: 'M17.8 6.5 a2.2 2.2 0 1 0 4.4 0 a2.2 2.2 0 1 0 -4.4 0 z M20 9 c7 7 7 14 0 18 c-7 -4 -7 -11 0 -18 z M14 27 h12 v3 h-12 z M16.5 30 h7 c0 8 4 10 4.5 17 h-16 c0.5 -7 4.5 -9 4.5 -17 z' + BASE,
  Knight: 'M12 47 c0 -9 5 -12 3.5 -19 c-3 -1.5 -5 -4 -3.5 -8 l6 -10 l1.5 -4 l2.5 4.5 c6 1.5 9.5 9 8.5 19 c-0.6 6 -1.5 12 -1.5 17.5 z' + BASE,
  Queen: 'M17.8 7 a2.2 2.2 0 1 0 4.4 0 a2.2 2.2 0 1 0 -4.4 0 z M10.5 13 l4.5 8 l2.5 -9 l2.5 9 l2.5 -9 l2.5 9 l4.5 -8 l-2.5 15 h-14 z' + BODY + BASE,
  King: 'M18.5 3 h3 v3.5 h3.5 v3 h-3.5 v5.5 h-3 v-5.5 h-3.5 v-3 h3.5 z M12.5 15 h15 l-2.5 13 h-10 z' + BODY + BASE,
}

export default function PieceIcon({ type, color, size = 24 }) {
  const white = color === 'white'
  return (
    <svg viewBox="0 0 40 56" width={size * (40 / 56)} height={size} role="img" aria-label={`${color} ${type.toLowerCase()}`}>
      <path
        d={SHAPES[type]}
        fill={white ? '#F4F6FA' : '#22262F'}
        stroke={white ? '#1B2230' : '#E3E8F0'}
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}
