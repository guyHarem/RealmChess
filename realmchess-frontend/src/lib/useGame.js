// Game state from the backend plus the local selection (which piece is picked up)
import { useCallback, useEffect, useRef, useState } from 'react'
import { OFFLINE, api, legalMovesOf, rememberSeat } from './api.js'
import { keyOf, parsePiece, sameCoord } from './chess.js'

const POLL_MS = 1000 // how often an online game asks whether the other player has done something

// which: a room id, or 'practice' for the lesson board
export function useGame(which = 'main') {
  const [game, setGame] = useState(null)
  const [selected, setSelected] = useState(null)
  const [legalMoves, setLegalMoves] = useState([])
  const [error, setError] = useState(null)
  const [gone, setGone] = useState(false) // the server no longer has this game
  const latest = useRef(null)

  const clearSelection = useCallback(() => {
    setSelected(null)
    setLegalMoves([])
  }, [])

  // Take in an answer that carries the whole game. Answers can arrive out of order (a slow
  // "what is the state?" after a quick move), so one older than what we show is dropped.
  const accept = useCallback((data) => {
    if (data.gone) setGone(true)
    if (data.board) {
      const shown = latest.current
      if (shown && shown.game_id === data.game_id && data.version < shown.version) return
      const next = { ...data, receivedAt: performance.now() }
      latest.current = next
      setGame(next)
    }
  }, [])

  // Every state-changing endpoint answers with the whole game
  const call = useCallback(async (path, body) => {
    try {
      const data = await api(path, body, which)
      accept(data)
      // A declined draw offer is an answer, not a fault: the page shows it its own way
      setError(data.success || data.draw_declined ? null : data.error)
      setSelected(null)
      setLegalMoves([])
      return data
    } catch {
      setError(OFFLINE)
      return null
    }
  }, [which, accept])

  useEffect(() => {
    let stopped = false
    let timer = null

    // In an online game, sit down if there is a free seat, then keep asking for news
    async function keepUp() {
      const current = latest.current
      if (stopped || !current || current.kind !== 'online') return
      try {
        const data = await api('/game/state?since=' + encodeURIComponent(current.stamp), undefined, which)
        if (stopped) return
        if (data.gone) setGone(true)
        else if (data.unchanged) {
          // Nothing happened; only who is connected may have changed
          if (JSON.stringify(data.online) !== JSON.stringify(current.online)) {
            latest.current = { ...current, online: data.online }
            setGame(latest.current)
          }
        } else if (data.board) {
          accept(data)
          setSelected(null)
          setLegalMoves([])
        }
        setError(null)
      } catch {
        setError(OFFLINE)
      }
      if (!stopped) timer = setTimeout(keepUp, POLL_MS)
    }

    async function begin() {
      try {
        let data = await api('/game/state', undefined, which)
        if (stopped) return
        if (data.kind === 'online' && !data.online.you) {
          data = await api('/game/join', {}, which)
          if (stopped) return
          if (data.seat) rememberSeat(which, data.seat)
        }
        accept(data)
        setError(null)
        timer = setTimeout(keepUp, POLL_MS)
      } catch {
        setError(OFFLINE)
      }
    }

    begin()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [which, accept])

  // Re-read the game without touching the selection (used when a clock runs out)
  const refresh = useCallback(async () => {
    try {
      accept(await api('/game/state', undefined, which))
    } catch {
      setError(OFFLINE)
    }
  }, [which, accept])

  // Ask the computer to think and play. A refusal still carries the current game, and is
  // normal when the position changed while it thought (undo, new game), so it shows no error.
  const computerMove = useCallback(async () => {
    try {
      const data = await api('/game/computer-move', {}, which)
      accept(data)
      return data
    } catch {
      setError(OFFLINE)
      return null
    }
  }, [which, accept])

  const select = useCallback(async (coord) => {
    try {
      const data = await legalMovesOf(coord, which)
      setSelected(coord)
      setLegalMoves(data.legal_moves ?? [])
    } catch {
      setError(OFFLINE)
    }
  }, [which])

  // One click on a cell: play the move if it is legal, otherwise pick up or put down a piece
  const clickCell = useCallback(
    (coord) => {
      if (!game || game.pending_promotion) return
      if (selected && legalMoves.some((move) => sameCoord(move, coord))) {
        call('/game/move', { from: selected, to: coord })
        return
      }
      const piece = parsePiece(game.board[keyOf(coord)])
      if (piece?.color === game.current_player && !sameCoord(selected, coord)) select(coord)
      else clearSelection()
    },
    [game, selected, legalMoves, call, select, clearSelection],
  )

  return {
    game,
    selected,
    legalMoves,
    error,
    gone,
    clickCell,
    clearSelection,
    select,
    refresh,
    computerMove,
    setup: (position) => call('/debug/setup', position),
    move: (from, to) => call('/game/move', { from, to }),
    resign: (color) => call('/game/resign', { color }),
    agreeDraw: () => call('/game/draw', {}),
    newGame: (options) => call('/game/new', options ?? {}),
    undo: () => call('/game/undo', {}),
    promote: (pieceType) => call('/game/promote', { coord: game.pending_promotion, piece_type: pieceType }),
    // Between online players: offer a draw or ask to take a move back, and answer one
    offer: (kind) => call('/game/offer', { kind }),
    answer: (yes) => call('/game/answer', { accept: yes }),
  }
}
