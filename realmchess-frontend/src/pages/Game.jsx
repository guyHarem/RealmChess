import { useEffect, useRef, useState } from 'react'
import Clock from '../components/Clock.jsx'
import CubeBoard from '../components/CubeBoard.jsx'
import Dialog from '../components/Dialog.jsx'
import LayerMap from '../components/LayerMap.jsx'
import Logo from '../components/Logo.jsx'
import MoveList from '../components/MoveList.jsx'
import PlayerCard from '../components/PlayerCard.jsx'
import TeamChat from '../components/TeamChat.jsx'
import { FULL_BOARD, LAYERS, capturedBy, capturedPoints, describeMove, keyOf, layerOf, layersOf, otherColor, parsePiece } from '../lib/chess.js'
import { navigate } from '../lib/router.js'
import { clockRequest, computerRequest, levelName, loadSettings, saveSettings } from '../lib/settings.js'
import { playSound } from '../lib/sound.js'
import { useGame } from '../lib/useGame.js'
import { usePhone } from '../lib/usePhone.js'

const NAMES = { white: 'White', black: 'Black' }
const PROMOTIONS = ['Queen', 'Rook', 'Bishop', 'Knight']

// How the game ended, as a headline and one line of detail. null while it is still going.
function outcomeOf(game) {
  if (!game) return null
  const computer = game.computer?.color
  const you = computer ? otherColor(computer) : game.online?.you
  const rival = computer ? 'The computer' : game.teams ? 'The other team' : 'Your opponent'
  // "White" when both sides are on this screen (or we are watching); otherwise "You" and
  // "The computer" / "Your opponent", with the verb form that goes with each
  const who = (color) => (!you ? NAMES[color] : color === you ? 'You' : rival)
  const has = (color) => (you && color === you ? 'have' : 'has')
  const is = (color) => (you && color === you ? 'are' : 'is')
  const lower = (name) => name.replace('The', 'the').replace('You', 'you')
  const wins = !game.winner ? 'Draw' : !you ? `${NAMES[game.winner]} wins` : game.winner === you ? 'You win' : `${rival} wins`
  if (game.status === 'checkmate') return { title: wins, detail: 'Checkmate.' }
  if (game.status === 'resigned') return { title: wins, detail: `${who(otherColor(game.winner))} resigned.` }
  if (game.status === 'timeout') {
    if (game.winner) return { title: wins, detail: `${who(otherColor(game.winner))} ran out of time.` }
    // The clock only runs for the player to move, so that is who ran out
    const late = game.current_player
    return {
      title: 'Draw',
      detail: `${who(late)} ran out of time, but ${lower(who(otherColor(late)))} ${has(otherColor(late))} too few pieces to checkmate.`,
    }
  }
  if (game.status === 'agreed_draw') {
    return { title: 'Draw', detail: computer ? 'The computer accepted your draw offer.' : 'Both players agreed to a draw.' }
  }
  const stuck = game.current_player
  const reasons = {
    stalemate: `${who(stuck)} ${has(stuck)} no legal move and ${is(stuck)} not in check.`,
    repetition: 'The same position came up three times.',
    move_limit: `Both players made ${game.move_limit} moves with no capture and no pawn move.`,
    insufficient_material: 'Neither side has enough pieces left to checkmate.',
  }
  return game.draw_reason ? { title: 'Draw', detail: reasons[game.draw_reason] } : null
}

// The rook's move in a castling (the history only records the king's): it comes from the
// corner on the king's side and lands next to the king, on the side it came from
function castlingRook(entry, size) {
  if (entry?.special_move !== 'castling') return null
  const [fx, y, z] = entry.from
  const direction = Math.sign(entry.to[0] - fx)
  return { from: [direction > 0 ? size - 1 : 0, y, z], to: [entry.to[0] - direction, y, z] }
}

// In a team game, which of a side's two players a seat is: "white2" is White 2
const seatNumber = (seat) => (seat?.endsWith('2') ? 2 : 1)
const seatName = (seat) => `${NAMES[seat.slice(0, 5)]} ${seatNumber(seat)}`

export default function Game({ id, joinSide = null }) {
  const {
    game, selected, legalMoves, error, gone, clickCell, newGame, undo, promote, resign, agreeDraw, refresh, computerMove,
    offer, answer, askHint, say, select, clearSelection,
  } = useGame(id, joinSide)
  const [settings, setSettings] = useState(loadSettings)
  const [flipped, setFlipped] = useState(false)
  const [activeLayer, setActiveLayer] = useState(0)
  const [spread, setSpread] = useState(false)
  const [solo, setSolo] = useState(false)
  const [command, setCommand] = useState(null)
  const [asking, setAsking] = useState(null) // 'resign' | 'draw'
  const [resultSeen, setResultSeen] = useState(false)
  const [declined, setDeclined] = useState(null) // number of moves played when the computer said no to a draw
  const [attempt, setAttempt] = useState(0)
  const [seenMoves, setSeenMoves] = useState(0)
  const [inviteClosed, setInviteClosed] = useState(false)
  const [copied, setCopied] = useState(null) // the link last copied
  const [menuOpen, setMenuOpen] = useState(false)
  const [hint, setHint] = useState(null) // the computer's suggestion: { from, to, version }
  const [thinking, setThinking] = useState(false) // waiting for a hint
  const phone = usePhone()
  const waiting = useRef(false)

  const board = game?.board ?? {}
  const history = game?.move_history ?? []
  const player = game?.current_player ?? 'white'
  const outcome = outcomeOf(game)
  const computer = game?.computer ?? null
  const human = computer ? otherColor(computer.color) : null
  const computerTurn = !!computer && !outcome && player === computer.color && !game.pending_promotion
  // An online game: which color is ours (null when watching), and what the other player is up to
  const online = game?.online ?? null
  const you = online?.you ?? null
  const rival = you ? otherColor(you) : null
  const watching = !!online && !you
  const friendMissing = !!online && Object.values(online.seats).some((taken) => !taken)
  const theirOffer = online?.offer && you && online.offer.by !== you ? online.offer : null
  const myOffer = online?.offer && online.offer.by === you ? online.offer : null
  const link = `${window.location.origin}${window.location.pathname}#/game/${id}`
  // A team game: two players a side take turns with the army. turnSeat is whose turn it is
  // ("black2": Black's second player); mySeat is ours online.
  const teams = !!game?.teams
  const turnSeat = game?.teams?.turn ?? player
  const mySeat = online?.seat ?? null
  const myTurn = !online || (teams ? mySeat === turnSeat : you === player)
  const freeSeats = (color) => Object.entries(online?.seats ?? {}).some(([seat, taken]) => !taken && seat.startsWith(color))
  // Who is up within a team: online and on one screen "White 2"; with the computer "Player 2"
  const turnName = computer ? `Player ${seatNumber(turnSeat)}` : seatName(turnSeat)
  // Online team games: on your teammate's turn you may suggest a move rather than play one
  const canSuggest = !!online && teams && !watching && !outcome && player === you && !myTurn && !game?.pending_promotion
  // A suggestion only counts for the position it was made in: a hint you asked for, or
  // (on your turn) the latest move your teammate suggested
  const shownHint = hint && game && hint.version === game.version ? hint : null
  const teammateIdea = myTurn && online && teams
    ? [...(online.chat ?? [])].reverse().find((message) => message.move && message.seat !== mySeat && message.version === game?.version)?.move ?? null
    : null
  const suggestion = shownHint ?? teammateIdea
  // Hints: against the computer and on one screen, never between people online
  const hintsAllowed = !!game && (!online || !!computer) && !watching
  // Our side sits nearest the camera, unless the view has been flipped
  const mine = you ?? human ?? settings.side
  const side = flipped ? otherColor(mine) : mine
  // The move just played, for the marker on the board (a promotion is recorded after its pawn move)
  const lastEntry = [...history].reverse().find((entry) => entry.special_move !== 'promotion')
  // What it captured, for the 3D board to fade out (not en passant: that pawn stood elsewhere)
  const lastMove = lastEntry
    ? {
        from: lastEntry.from,
        to: lastEntry.to,
        index: history.lastIndexOf(lastEntry),
        captured: lastEntry.special_move === 'en_passant' ? null : parsePiece(lastEntry.captured_piece),
      }
    : null
  const size = game?.board_size?.size ?? FULL_BOARD.size
  // What glides on the 3D board: the move just played (with the rook when castling), or after
  // a take-back the pieces going back to where they were
  const [glideState, setGlideState] = useState({ length: 0, last: null, glides: null })
  if (history.length !== glideState.length || history.at(-1) !== glideState.last) {
    const before = glideState
    const undone = history.length < before.length
      ? before.entries.slice(history.length).filter((entry) => entry.special_move !== 'promotion').reverse()
      : []
    const back = (entry) => ({ from: entry.to, to: entry.from })
    setGlideState({
      length: history.length,
      last: history.at(-1),
      entries: history,
      glides: undone.length > 0 && before.length > 0
        ? undone.flatMap((entry) => [back(entry), ...(castlingRook(entry, size) ? [back(castlingRook(entry, size))] : [])])
        : lastMove
          ? [lastMove, ...(castlingRook(lastEntry, size) ? [castlingRook(lastEntry, size)] : [])]
          : null,
    })
  }
  const glides = glideState.glides

  // The king of the side to move, while it is in check (or checkmated)
  const inCheck = game?.status === 'check' || game?.status === 'checkmate'
  const checkKey = inCheck ? Object.keys(board).find((key) => board[key] === `King(${player})`) : null
  const check = checkKey ? JSON.parse(checkKey) : null
  const captured = capturedBy(history)
  const points = capturedPoints(captured)
  const layers = game?.board_size ? layersOf(game.board_size) : FULL_BOARD.layers
  const shownLayer = layers.includes(activeLayer) ? activeLayer : 0
  const quiet = game ? Math.floor(game.halfmove_clock / 2) : 0

  // When the computer or the online opponent moves, bring the layer it moved to forward
  if (history.length !== seenMoves) {
    setSeenMoves(history.length)
    const mover = parsePiece(lastEntry?.moving_piece)?.color
    if (lastEntry && (teams || mover === (computer?.color ?? rival))) setActiveLayer(lastEntry.to[2])
  }

  const send = (type, direction) => setCommand({ id: Date.now(), type, direction })

  // A sound for every new move (not for the moves already there when the page opens, nor for
  // take-backs), and one when the game ends
  const heard = useRef(null) // { moves, over } as last heard
  const over = !!outcome
  useEffect(() => {
    if (!game) return
    const moves = game.move_history
    const before = heard.current
    heard.current = { moves: moves.length, over }
    if (!before || !settings.sound) return
    if (over && !before.over) playSound('end')
    // (a promotion is its own history entry after the pawn's move, which already sounded)
    else if (moves.length > before.moves && !over && moves.at(-1).special_move !== 'promotion') {
      playSound(moves.at(-1).captured_piece ? 'capture' : game.status === 'check' ? 'check' : 'move')
    }
  }, [game, over, settings.sound])

  function toggleSound() {
    const next = { ...settings, sound: !settings.sound }
    setSettings(next)
    saveSettings(next)
    if (next.sound) playSound('move') // and the first tap is what lets the browser play sound
  }

  // On the computer's turn, ask the server for its move. The short wait lets your own move
  // be seen first. One request at a time; when it comes back the effect runs again, which
  // covers a move thrown away because the game changed while the computer was thinking.
  useEffect(() => {
    if (!computerTurn || waiting.current) return undefined
    const timer = setTimeout(async () => {
      waiting.current = true
      const data = await computerMove()
      waiting.current = false
      if (data?.success) {
        setAttempt((count) => count + 1)
      } else {
        // Thrown away because the game changed: ask again at once. Turned away because the
        // server is busy, or no answer at all: give it a little time first.
        const pause = !data ? 3000 : data.busy || data.slow_down ? 2000 : 300
        setTimeout(() => setAttempt((count) => count + 1), pause)
      }
    }, 450)
    return () => clearTimeout(timer)
  }, [computerTurn, history.length, attempt, computerMove])

  function onCellClick(coord) {
    if (canSuggest) {
      suggestWith(coord)
      return
    }
    if (outcome || computerTurn || !myTurn) return
    // Picking up a piece on another layer brings that layer forward
    const piece = parsePiece(board[keyOf(coord)])
    const isTarget = legalMoves.some((move) => keyOf(move) === keyOf(coord))
    if (!isTarget && piece?.color === player) setActiveLayer(coord[2])
    clickCell(coord)
  }

  // On a teammate's turn, picking a piece and a square suggests that move instead of playing it
  function suggestWith(coord) {
    if (selected && legalMoves.some((move) => keyOf(move) === keyOf(coord))) {
      say('', { from: selected, to: coord })
      return
    }
    const piece = parsePiece(board[keyOf(coord)])
    if (piece?.color === you && keyOf(coord) !== keyOf(selected ?? [])) {
      setActiveLayer(coord[2])
      select(coord)
    } else clearSelection()
  }

  async function showHint() {
    setThinking(true)
    const data = await askHint()
    setThinking(false)
    if (data?.hint) {
      setHint(data.hint)
      setActiveLayer(data.hint.from[2])
    }
  }

  function restart() {
    if (online) {
      navigate('/setup') // an online game is replayed by making a new one and sending its link
      return
    }
    // (a team game on this screen stays one: the room keeps its teams)
    setResultSeen(false)
    setAsking(null)
    newGame({
      rocks: settings.rocks,
      move_limit: settings.moveLimit,
      clock: clockRequest(settings.clock),
      computer: computerRequest(settings),
    })
  }

  async function offerDraw() {
    setAsking(null)
    if (online) {
      // Against the computer online it answers at once; a refusal shows as a note
      offer('draw')
      return
    }
    const data = await agreeDraw()
    if (data?.draw_declined) setDeclined(data.move_history.length)
  }

  function takeBack() {
    setResultSeen(false)
    if (online) offer('takeback')
    else undo()
  }

  async function copyLink(text) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(text)
    } catch {
      setCopied(null) // the link is on screen to select by hand
    }
  }

  // Whether every seat of a side is connected (a side the computer plays has none)
  const seatsOf = (color) => Object.keys(online?.seats ?? {}).filter((seat) => seat.startsWith(color))
  const allConnected = (color) => seatsOf(color).every((seat) => online.connected[seat])
  const nameOf = (color) => {
    if (color === computer?.color) return `Computer, ${levelName(computer.level)}`
    if (!online) {
      if (teams) return computer ? 'Player 1 and Player 2' : `${NAMES[color]} 1 and ${NAMES[color]} 2`
      if (computer) return 'You'
      return color === 'white' ? 'Player 1' : 'Player 2'
    }
    if (freeSeats(color)) return 'Waiting to join'
    const label = color === you
      ? (teams ? 'You and your teammate' : 'You')
      : watching ? (teams ? 'Team' : 'Player') : (teams ? 'The other team' : 'Opponent')
    if (color === you && !teams) return label
    if (allConnected(color)) return label
    return `${label}, ${teams ? 'someone not connected' : 'not connected'}`
  }
  const noteOf = (color) => {
    if (outcome || player !== color) return undefined
    if (color === computer?.color) return 'Thinking'
    const check = game?.status === 'check' ? ', in check' : ''
    if (online && color !== you) {
      if (freeSeats(color)) return 'Waiting to join'
      const whose = watching ? (teams ? `${turnName} to move` : 'To move') : (teams ? `${turnName}'s move` : 'Their move')
      return `${whose}${online.connected[turnSeat] ? '' : ', not connected'}`
    }
    if (teams) {
      if (online) return myTurn ? `Your move${check}` : `Your teammate's move${check}`
      return `${turnName} to move${check}`
    }
    return check ? 'Your move, in check' : undefined
  }
  let turnText = `${NAMES[player]} to move`
  if (online && friendMissing && !watching) {
    turnText = teams ? 'Waiting for players to join' : phone ? 'Waiting for your friend' : 'Waiting for your friend to join'
  } else if (computerTurn) turnText = 'The computer is thinking'
  else if (online && !watching) {
    turnText = myTurn ? 'Your move' : player === you ? "Your teammate's move" : teams ? "The other team's move" : "Your opponent's move"
  } else if (online && teams) turnText = `${turnName} to move`
  else if (computer) turnText = teams ? `${turnName}'s move` : 'Your move'
  else if (teams) turnText = `${turnName} to move`

  // You can ask to take a move back once you have made one
  const myMoves = history.filter((entry) => parsePiece(entry.moving_piece)?.color === you).length
  const undoDisabled = online
    ? watching || !!outcome || !!online.offer || myMoves === 0 || computerTurn
    : !settings.allowUndo || history.length === 0
  const offerDisabled = !!outcome || watching || !!online?.offer

  if (gone) {
    return (
      <div className="page">
        <header className="bar">
          <Logo />
          <a className="bar-link" href="#/">
            Back to home
          </a>
        </header>
        <main className="soon">
          <h1>This game is no longer here</h1>
          <p>Games are kept for a day after their last move, and are lost if the server restarts.</p>
          <a className="button button-primary" href="#/setup">
            Set up a new game
          </a>
        </main>
      </div>
    )
  }

  const card = (color, compact = false) => (
    <PlayerCard
      compact={compact}
      color={color}
      name={nameOf(color)}
      toMove={!outcome && player === color}
      note={noteOf(color)}
      points={points[color]}
      lead={points[color] - points[otherColor(color)]}
      captured={captured[color]}
      clock={game?.clock && <Clock clock={game.clock} color={color} receivedAt={game.receivedAt} onFlag={refresh} />}
    />
  )

  // The page's parts, arranged one way on a wide screen and another on a phone
  const turnPill = (
    <div className={`turn turn-${outcome ? 'over' : player}`} aria-live="polite">
      {!outcome && <i className={`chip chip-${player}`} />}
      {outcome ? outcome.title : turnText}
      {!outcome && game?.status === 'check' && <span className="turn-check">Check</span>}
    </div>
  )
  const barActions = (
    <div className="bar-actions">
      <button type="button" className="button" onClick={restart}>
        New game
      </button>
      <a className="button" href="#/">
        Exit
      </a>
    </div>
  )
  const actionButtons = (
    <>
      {hintsAllowed && (
        <button
          type="button"
          className="button button-hint"
          disabled={thinking || !!outcome || computerTurn || !myTurn || !!game.pending_promotion || !!shownHint}
          onClick={showHint}
        >
          {thinking ? 'Thinking…' : 'Hint'}
        </button>
      )}
      <div className="button-grid">
        <button type="button" className="button" disabled={undoDisabled} onClick={takeBack}>
          {online && !computer ? 'Ask to take back' : 'Undo move'}
        </button>
        <button type="button" className="button" disabled={offerDisabled} onClick={() => setAsking('draw')}>
          Offer draw
        </button>
        <button type="button" className="button" disabled={!!outcome || watching} onClick={() => setAsking('resign')}>
          Resign
        </button>
        <button type="button" className="button" onClick={() => setFlipped(!flipped)}>
          Flip side
        </button>
      </div>
      <p className="quiet">
        {quiet} of {game?.move_limit ?? settings.moveLimit} quiet moves. The game is drawn at the limit, when
        nobody captures or moves a pawn.
      </p>
    </>
  )
  const notices = (
    <>
      {shownHint && <p className="banner-hint">Hint: {describeMove(board, shownHint)}.</p>}
      {teammateIdea && !shownHint && (
        <p className="banner-hint">Your teammate suggests {describeMove(board, teammateIdea)}.</p>
      )}
      {declined === history.length && !outcome && <p className="banner-note">The computer declines the draw.</p>}
      {watching && <p className="banner-note">You are watching this game.</p>}
      {myOffer && !outcome && (
        <p className="banner-note">
          {teams
            ? myOffer.kind === 'draw' ? 'Your team offered a draw.' : 'Your team asked to take a move back.'
            : myOffer.kind === 'draw' ? 'You offered a draw.' : 'You asked to take your move back.'}{' '}
          Waiting for an answer.{' '}
          <button type="button" className="link-button" onClick={() => answer(false)}>
            Withdraw
          </button>
        </p>
      )}
      {online && friendMissing && !watching && inviteClosed && (
        <p className="banner-note">
          {teams ? 'Not everyone has joined yet.' : 'Your friend has not joined yet.'}{' '}
          <button type="button" className="link-button" onClick={() => setInviteClosed(false)}>
            {teams ? 'Show the links' : 'Show the link'}
          </button>
        </p>
      )}
      {error && <p className="banner-error">{error}</p>}
    </>
  )
  const layerPicker = (
    <div className="layer-picker" role="group" aria-label="Current layer">
      {LAYERS.filter((layer) => layers.includes(layer.z)).map((layer) => (
        <button
          key={layer.z}
          type="button"
          className={`button layer-button ${shownLayer === layer.z ? 'is-selected' : ''}`}
          aria-pressed={shownLayer === layer.z}
          style={shownLayer === layer.z ? { background: layer.light, borderColor: layer.light } : undefined}
          onClick={() => setActiveLayer(layer.z)}
        >
          <i className="swatch" style={{ background: layer.dark }} />
          {layer.name}
        </button>
      ))}
    </div>
  )
  const boardFrame = (
    <div className="board-frame">
      <CubeBoard
        board={board}
        size={size}
        layers={layers}
        activeLayer={shownLayer}
        selected={selected}
        legalMoves={legalMoves}
        lastMove={lastMove}
        glides={glides}
        check={check}
        suggestion={suggestion}
        showMoveBalls={settings.showLegalMoves}
        spread={spread}
        solo={solo}
        side={side}
        command={command}
        onCellClick={onCellClick}
      />

      {online && friendMissing && !watching && !inviteClosed && !teams && (
        <Dialog
          title="Invite your friend"
          actions={
            <>
              <button type="button" className="button button-primary" onClick={() => copyLink(link)}>
                {copied === link ? 'Copied' : 'Copy link'}
              </button>
              <button type="button" className="button" onClick={() => setInviteClosed(true)}>
                Close
              </button>
            </>
          }
        >
          <p>Send this link. Whoever opens it first plays {NAMES[rival]}; anyone after that can watch.</p>
          <input className="invite-link" readOnly value={link} aria-label="Game link" onFocus={(event) => event.target.select()} />
        </Dialog>
      )}

      {online && friendMissing && !watching && !inviteClosed && teams && (
        <Dialog
          title="Invite the players"
          actions={
            <button type="button" className="button" onClick={() => setInviteClosed(true)}>
              Close
            </button>
          }
        >
          <p>Each link seats whoever opens it on that side, until the side is full. Anyone after that can watch.</p>
          {[you, rival].filter((color) => freeSeats(color)).map((color) => (
            <div key={color} className="invite-row">
              <label htmlFor={`invite-${color}`}>{color === you ? 'Your teammate' : `The other team (${NAMES[color]})`}</label>
              <div className="invite-copy">
                <input
                  id={`invite-${color}`}
                  className="invite-link"
                  readOnly
                  value={`${link}/${color}`}
                  onFocus={(event) => event.target.select()}
                />
                <button type="button" className="button button-primary" onClick={() => copyLink(`${link}/${color}`)}>
                  {copied === `${link}/${color}` ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>
          ))}
        </Dialog>
      )}

      {theirOffer && !outcome && (
        <Dialog
          title={
            teams
              ? theirOffer.kind === 'draw' ? 'The other team offers a draw' : 'The other team asks to take a move back'
              : theirOffer.kind === 'draw' ? 'Your opponent offers a draw' : 'Your opponent asks to take a move back'
          }
          actions={
            <>
              <button type="button" className="button button-primary" onClick={() => answer(true)}>
                {theirOffer.kind === 'draw' ? 'Accept draw' : 'Allow it'}
              </button>
              <button type="button" className="button" onClick={() => answer(false)}>
                {theirOffer.kind === 'draw' ? 'Decline' : 'Refuse'}
              </button>
            </>
          }
        >
          <p>
            {theirOffer.kind === 'draw'
              ? 'If you accept, the game ends as a draw.'
              : player === you
                ? 'Their last move and your reply would both be taken back.'
                : 'Their last move would be taken back.'}
          </p>
        </Dialog>
      )}

      {game?.pending_promotion && player !== computer?.color && myTurn && (
        <Dialog
          title="Promote your pawn"
          actions={PROMOTIONS.map((type) => (
            <button key={type} type="button" className="button" onClick={() => promote(type)}>
              {type}
            </button>
          ))}
        >
          <p>Choose the piece it becomes.</p>
        </Dialog>
      )}

      {asking === 'resign' && (
        <Dialog
          title={computer || online ? 'Resign this game?' : `${NAMES[player]}, resign this game?`}
          actions={
            <>
              <button
                type="button"
                className="button button-danger"
                onClick={() => {
                  resign(human ?? player)
                  setAsking(null)
                }}
              >
                Resign
              </button>
              <button type="button" className="button" onClick={() => setAsking(null)}>
                Keep playing
              </button>
            </>
          }
        >
          <p>
            {computer
              ? 'The computer will win.'
              : online ? (teams ? 'The other team will win.' : 'Your opponent will win.') : `${NAMES[otherColor(player)]} will win.`}
          </p>
        </Dialog>
      )}

      {asking === 'draw' && online && !computer && (
        <Dialog
          title="Offer your opponent a draw?"
          actions={
            <>
              <button type="button" className="button button-primary" onClick={offerDraw}>
                Offer draw
              </button>
              <button type="button" className="button" onClick={() => setAsking(null)}>
                Keep playing
              </button>
            </>
          }
        >
          <p>They can accept or decline. Making a move declines it.</p>
        </Dialog>
      )}

      {asking === 'draw' && !computer && !online && (
        <Dialog
          title={`${teams ? `${NAMES[player]} team` : NAMES[player]} offers a draw`}
          actions={
            <>
              <button type="button" className="button button-primary" onClick={offerDraw}>
                Accept draw
              </button>
              <button type="button" className="button" onClick={() => setAsking(null)}>
                Decline
              </button>
            </>
          }
        >
          <p>{NAMES[otherColor(player)]}, do you accept?</p>
        </Dialog>
      )}

      {asking === 'draw' && computer && (
        <Dialog
          title="Offer the computer a draw?"
          actions={
            <>
              <button type="button" className="button button-primary" onClick={offerDraw}>
                Offer draw
              </button>
              <button type="button" className="button" onClick={() => setAsking(null)}>
                Keep playing
              </button>
            </>
          }
        >
          <p>It accepts when it thinks it is worse, or when a long game is level.</p>
        </Dialog>
      )}

      {outcome && !resultSeen && !asking && (
        <Dialog
          title={outcome.title}
          actions={
            <>
              <button type="button" className="button button-primary" onClick={restart}>
                New game
              </button>
              <button type="button" className="button" onClick={() => setResultSeen(true)}>
                Look at the board
              </button>
            </>
          }
        >
          <p>{outcome.detail}</p>
        </Dialog>
      )}
    </div>
  )
  const viewControls = (
    <div className="view-controls">
      <button type="button" className="button" onClick={() => send('turn', -1)}>
        Turn left
      </button>
      <button type="button" className="button" onClick={() => send('turn', 1)}>
        Turn right
      </button>
      <button type="button" className="button" onClick={() => send('reset')}>
        Reset view
      </button>
      <button type="button" className={`button ${spread ? 'is-on' : ''}`} aria-pressed={spread} onClick={() => setSpread(!spread)}>
        Spread layers
      </button>
      <button type="button" className={`button ${solo ? 'is-on' : ''}`} aria-pressed={solo} onClick={() => setSolo(!solo)}>
        Only this layer
      </button>
      <button type="button" className={`button ${settings.sound ? 'is-on' : ''}`} aria-pressed={settings.sound} onClick={toggleSound}>
        Sound
      </button>
    </div>
  )
  const topView = (
    <section>
      <h2>{layerOf(shownLayer).name}, seen from above</h2>
      <LayerMap
        board={board}
        size={size}
        z={shownLayer}
        side={side}
        selected={selected}
        legalMoves={legalMoves}
        lastMove={lastMove}
        suggestion={suggestion}
        showMoves={settings.showLegalMoves}
        onCellClick={onCellClick}
      />
    </section>
  )
  const teamChat = online && teams && !watching && (
    <TeamChat
      messages={online.chat ?? []}
      mySeat={mySeat}
      canSuggest={canSuggest}
      describe={(message) => describeMove(board, message.move)}
      onSay={(text) => say(text)}
    />
  )
  const moveList = <MoveList history={history} currentPlayer={player} finished={!!outcome} />

  if (phone) {
    // One screen, no scrolling: the 3D board for the overview, the top view for tapping,
    // and everything that is not needed on every move behind the Menu button
    return (
      <div className="game is-phone">
        <header className="bar">
          <Logo />
          {turnPill}
          <button type="button" className="button" aria-haspopup="dialog" onClick={() => setMenuOpen(true)}>
            Menu
          </button>
        </header>

        <main className="phone-main">
          {card(otherColor(side), true)}
          <div className="phone-notices">{notices}</div>
          {boardFrame}
          {layerPicker}
          {topView}
          {card(side, true)}
        </main>

        {menuOpen && (
          // Choosing anything in the menu closes it, so the board is back in view
          <div
            className="sheet"
            role="dialog"
            aria-modal="true"
            aria-label="Game menu"
            onClick={(event) => event.target.closest('button, a') && setMenuOpen(false)}
          >
            <div className="sheet-head">
              <h2>Game menu</h2>
              <button type="button" className="button">
                Close
              </button>
            </div>
            <div className="game-actions">{actionButtons}</div>
            {teamChat}
            {viewControls}
            {moveList}
            {barActions}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="game">
      <header className="bar">
        <Logo />
        {turnPill}
        {barActions}
      </header>

      <main className="game-main">
        <aside className="game-left">
          {card(otherColor(side))}
          <div className="game-actions">
            {actionButtons}
            {notices}
          </div>
          {card(side)}
        </aside>

        <section className="game-centre">
          {layerPicker}
          {boardFrame}
          {viewControls}
        </section>

        <aside className="game-right">
          {topView}
          {teamChat}
          {moveList}
        </aside>
      </main>
    </div>
  )
}
