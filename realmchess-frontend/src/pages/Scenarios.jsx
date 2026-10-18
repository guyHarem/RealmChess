// Scenarios: checkmate puzzles that start easy and get harder.
// #/scenarios is the list, #/scenarios/<id> plays one. They run on the server's practice game.
import { useCallback, useEffect, useRef, useState } from 'react'
import CubeBoard from '../components/CubeBoard.jsx'
import LayerMap from '../components/LayerMap.jsx'
import LayerPicker from '../components/LayerPicker.jsx'
import Logo from '../components/Logo.jsx'
import { boardFromPieces, keyOf, layerOf, layersOf, parsePiece, sameCoord } from '../lib/chess.js'
import { useGame } from '../lib/useGame.js'
import collection from '../scenarios.json'

const TIERS = collection.tiers
const ALL = TIERS.flatMap((tier) => tier.scenarios.map((scenario, index) => ({ ...scenario, tier, number: index + 1 })))
const STORE = 'realmchess.scenarios'
const GOALS = { 1: 'Checkmate in one move.', 2: 'Checkmate in two moves.' }

function loadSolved() {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? '[]')
  } catch {
    return []
  }
}

function Header({ back }) {
  return (
    <header className="bar">
      <Logo />
      <a className="bar-link" href={back.href}>
        {back.label}
      </a>
    </header>
  )
}

// ---------- the list ----------

function List() {
  const solved = loadSolved()
  const next = ALL.find((scenario) => !solved.includes(scenario.id)) ?? ALL[0]
  const [picked, setPicked] = useState(next.id)
  const scenario = ALL.find((item) => item.id === picked) ?? next

  return (
    <div className="page">
      <Header back={{ href: '#/', label: 'Back to home' }} />
      <main className="scenarios-main">
        <div className="scenarios-list">
          <div className="scenarios-intro">
            <h1>Scenarios</h1>
            <p>Each scenario is a position where White can force checkmate. They start easy and get harder.</p>
            <p className="help">Progress is kept only while this tab stays open.</p>
          </div>

          {TIERS.map((tier) => (
            <section key={tier.id} className="tier">
              <h2>
                {tier.name} <span>{tier.note}</span>
              </h2>
              <div className="tiles">
                {tier.scenarios.map((item, index) => {
                  const state = solved.includes(item.id) ? 'solved' : item.id === next.id ? 'next' : ''
                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`tile ${state ? `is-${state}` : ''} ${item.id === scenario.id ? 'is-picked' : ''}`}
                      aria-pressed={item.id === scenario.id}
                      aria-label={`${tier.name} scenario ${index + 1}${state ? `, ${state}` : ''}`}
                      onClick={() => setPicked(item.id)}
                    >
                      <strong>{index + 1}</strong>
                      <small>{state}</small>
                    </button>
                  )
                })}
              </div>
            </section>
          ))}
        </div>

        <aside className="scenario-preview">
          <div>
            <p className="help">
              {scenario.tier.name}, scenario {scenario.number}
            </p>
            <h2>
              <i className="chip chip-white" />
              White to move
            </h2>
            <p>{GOALS[scenario.tier.mateIn]}</p>
          </div>
          <div className="scenario-picture">
            <CubeBoard
              interactive={false}
              board={boardFromPieces(scenario.pieces, scenario.tier.rocks)}
              size={scenario.tier.board.size}
              layers={layersOf(scenario.tier.board)}
              activeLayer={scenario.layer}
            />
          </div>
          <a className="button button-primary button-large" href={`#/scenarios/${scenario.id}`}>
            Start scenario
          </a>
        </aside>
      </main>
    </div>
  )
}

// ---------- playing one ----------

function Play({ scenario }) {
  const { game, selected, legalMoves, error, clickCell, clearSelection, select, setup, move } = useGame('practice')
  const { tier, solution } = scenario
  const layers = layersOf(tier.board)
  // 'key': find the first move. 'reply': Black is answering. 'finish': deliver mate. 'solved'.
  const [phase, setPhase] = useState('key')
  const [activeLayer, setActiveLayer] = useState(scenario.layer)
  const [hints, setHints] = useState(0)
  const [nudge, setNudge] = useState(null)
  const [justSolved, setJustSolved] = useState(false)
  const timer = useRef(null)

  const board = game?.board_size?.size === tier.board.size ? game.board : {}
  const index = ALL.findIndex((item) => item.id === scenario.id)
  const following = ALL[index + 1]

  const lay = useCallback(() => {
    clearTimeout(timer.current)
    setPhase('key')
    setHints(0)
    setNudge(null)
    setJustSolved(false)
    setActiveLayer(scenario.layer)
    setup({ ...tier.board, rocks: tier.rocks, current_player: 'white', pieces: scenario.pieces })
    // setup is recreated every render but always talks to the same practice game
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario])

  useEffect(() => {
    lay()
    return () => clearTimeout(timer.current)
  }, [lay])

  function markSolved() {
    setPhase('solved')
    setJustSolved(true)
    const solved = loadSolved()
    if (!solved.includes(scenario.id)) {
      try {
        sessionStorage.setItem(STORE, JSON.stringify([...solved, scenario.id]))
      } catch {
        // Progress is only a convenience; carry on without it
      }
    }
  }

  // The moves that are right at this point: the key move, then any of the mating moves
  const wanted = phase === 'key' ? [solution.key] : phase === 'finish' ? solution.mates : []

  function onCellClick(coord) {
    if (!game || (phase !== 'key' && phase !== 'finish')) return
    const isMove = selected && legalMoves.some((candidate) => sameCoord(candidate, coord))
    if (!isMove) {
      const piece = parsePiece(board[keyOf(coord)])
      if (piece?.color === 'white') setActiveLayer(coord[2])
      setNudge(null)
      clickCell(coord)
      return
    }
    const right = wanted.some((answer) => sameCoord(answer.from, selected) && sameCoord(answer.to, coord))
    if (!right) {
      clearSelection()
      setNudge(
        phase === 'key' && tier.mateIn === 2
          ? 'After that move Black can escape. Look for the move that leaves no defence.'
          : 'That is not checkmate. Try again.',
      )
      return
    }
    clickCell(coord)
    setNudge(null)
    setHints(0)
    setActiveLayer(coord[2])
    if (phase === 'finish' || tier.mateIn === 1) {
      markSolved()
      return
    }
    // Black makes its best defence, then it is your move again
    setPhase('reply')
    timer.current = setTimeout(async () => {
      await move(solution.reply.from, solution.reply.to)
      setActiveLayer(solution.reply.to[2])
      setPhase('finish')
    }, 900)
  }

  function hint() {
    const answer = wanted[0]
    if (!answer) return
    setNudge(null)
    setHints(Math.min(2, hints + 1))
    setActiveLayer(hints === 0 ? answer.from[2] : answer.to[2])
    select(answer.from)
  }

  const goal = hints >= 2 && wanted[0] ? wanted[0].to : null
  const prompts = {
    key: tier.mateIn === 2 ? 'Find the first move. Black will answer, then you finish it.' : 'Find the move that is checkmate.',
    reply: 'Good. Black is answering.',
    finish: 'Black has moved. Now deliver checkmate.',
    solved: 'Checkmate. Solved.',
  }

  return (
    <div className="solve">
      <Header back={{ href: '#/scenarios', label: 'All scenarios' }} />
      <main className="solve-main">
        <aside className="solve-info">
          <div>
            <p className="help">
              {tier.name}, scenario {scenario.number} of {tier.scenarios.length}
            </p>
            <h1>
              <i className="chip chip-white" />
              White to move
            </h1>
            <p className="solve-goal">{GOALS[tier.mateIn]}</p>
          </div>

          <div className={`task ${phase === 'solved' ? 'is-solved' : ''}`} aria-live="polite">
            {prompts[phase]}
            {nudge && <span className="task-nudge">{nudge}</span>}
            {error && <span className="task-nudge">{error}</span>}
          </div>

          <div className="solve-actions">
            <button type="button" className="button" disabled={phase === 'solved' || phase === 'reply'} onClick={hint}>
              {hints === 0 ? 'Hint: which piece' : 'Hint: where to'}
            </button>
            <button type="button" className="button" onClick={lay}>
              Start over
            </button>
            {following ? (
              <a className={`button button-primary ${justSolved ? '' : 'is-quiet'}`} href={`#/scenarios/${following.id}`}>
                Next scenario
              </a>
            ) : (
              <a className={`button button-primary ${justSolved ? '' : 'is-quiet'}`} href="#/scenarios">
                Back to the list
              </a>
            )}
          </div>
        </aside>

        <section className="solve-board">
          <LayerPicker layers={layers} value={activeLayer} onChange={setActiveLayer} />
          <div className="board-frame">
            <CubeBoard
              board={board}
              size={tier.board.size}
              layers={layers}
              activeLayer={activeLayer}
              selected={selected}
              legalMoves={legalMoves}
              goal={goal}
              onCellClick={onCellClick}
            />
          </div>
        </section>

        <aside className="solve-side">
          <h2>{layerOf(activeLayer).name}, seen from above</h2>
          <LayerMap
            board={board}
            size={tier.board.size}
            z={activeLayer}
            side="white"
            selected={selected}
            legalMoves={legalMoves}
            goal={goal}
            onCellClick={onCellClick}
          />
          <p className="help">Pick a layer above the board to look at it here. A legal move on another layer shows as a ball inside the cube.</p>
        </aside>
      </main>
    </div>
  )
}

export default function Scenarios({ id }) {
  const scenario = ALL.find((item) => item.id === id)
  // The key makes a fresh player for each scenario, so nothing carries over from the last one
  return scenario ? <Play key={scenario.id} scenario={scenario} /> : <List />
}
