// Lesson player: read a short explanation, then make the move yourself on a small board.
// The lessons run on the server's separate "practice" game, so a real game in progress is untouched.
import { useCallback, useEffect, useState } from 'react'
import CubeBoard from '../components/CubeBoard.jsx'
import LayerMap from '../components/LayerMap.jsx'
import Logo from '../components/Logo.jsx'
import { LAYERS, keyOf, layerOf, layersOf, parsePiece, sameCoord } from '../lib/chess.js'
import { useGame } from '../lib/useGame.js'
import course from '../lessons.json'

const LESSONS = course.lessons
const BOARD = course.board
const BOARD_LAYERS = layersOf(BOARD)
const STORE = 'realmchess.lessons'

function loadDone() {
  try {
    return JSON.parse(sessionStorage.getItem(STORE) ?? '[]')
  } catch {
    return []
  }
}

export default function Learn() {
  const { game, selected, legalMoves, error, clickCell, clearSelection, select, setup } = useGame('practice')
  const [lessonIndex, setLessonIndex] = useState(() => {
    const first = LESSONS.findIndex((lesson) => !loadDone().includes(lesson.id))
    return first === -1 ? 0 : first
  })
  const [stepIndex, setStepIndex] = useState(0)
  const [solved, setSolved] = useState(false)
  const [revealed, setRevealed] = useState(false)
  const [nudge, setNudge] = useState(null)
  const [activeLayer, setActiveLayer] = useState(0)
  const [done, setDone] = useState(loadDone)

  const lesson = LESSONS[lessonIndex]
  const step = lesson.steps[stepIndex]
  const lastStep = stepIndex === lesson.steps.length - 1
  const lastLesson = lessonIndex === LESSONS.length - 1
  const board = game?.board_size?.size === BOARD.size ? game.board : {}

  // Put the step's position on the practice board
  const lay = useCallback(
    (which) => {
      setSolved(false)
      setRevealed(false)
      setNudge(null)
      setActiveLayer(which.layer)
      setup({ ...BOARD, rocks: false, current_player: 'white', pieces: which.pieces })
    },
    // setup is recreated every render but always talks to the same practice game
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  useEffect(() => {
    lay(LESSONS[lessonIndex].steps[stepIndex])
  }, [lessonIndex, stepIndex, lay])

  function open(index) {
    setLessonIndex(index)
    setStepIndex(0)
  }

  function finishLesson() {
    if (!done.includes(lesson.id)) {
      const next = [...done, lesson.id]
      setDone(next)
      try {
        sessionStorage.setItem(STORE, JSON.stringify(next))
      } catch {
        // Progress is only a convenience; carry on without it
      }
    }
  }

  async function onCellClick(coord) {
    if (solved || !game) return
    const isMove = selected && legalMoves.some((move) => sameCoord(move, coord))
    if (!isMove) {
      const piece = parsePiece(board[keyOf(coord)])
      if (piece?.color === 'white') setActiveLayer(coord[2])
      setNudge(null)
      clickCell(coord)
      return
    }
    // A legal move: only the one the lesson asks for is played
    if (sameCoord(selected, step.from) && sameCoord(coord, step.to)) {
      await clickCell(coord)
      setSolved(true)
      setNudge(null)
      setActiveLayer(coord[2])
      if (lastStep) finishLesson()
    } else {
      clearSelection()
      setNudge('That move is legal, but it is not the one this task asks for. Try again.')
    }
  }

  function showMe() {
    setRevealed(true)
    setNudge(null)
    setActiveLayer(step.from[2])
    select(step.from)
  }

  function next() {
    if (!lastStep) setStepIndex(stepIndex + 1)
    else if (!lastLesson) open(lessonIndex + 1)
  }

  const showGoal = !solved && (!step.hideGoal || revealed)

  return (
    <div className="learn">
      <header className="bar">
        <Logo />
        <a className="bar-link" href="#/">
          Back to home
        </a>
      </header>

      <main className="learn-main">
        <nav className="lesson-list" aria-label="Lessons">
          <h2>Lessons</h2>
          {LESSONS.map((item, index) => {
            const state = index === lessonIndex ? 'is-current' : done.includes(item.id) ? 'is-done' : ''
            return (
              <button
                key={item.id}
                type="button"
                className={`lesson-link ${state}`}
                aria-current={index === lessonIndex ? 'step' : undefined}
                aria-label={`Lesson ${index + 1}: ${item.title}${done.includes(item.id) ? ' (done)' : ''}`}
                onClick={() => open(index)}
              >
                <span className="lesson-mark" aria-hidden="true" />
                {/* On a phone the list is a row of numbers; the title is shown below it */}
                <span className="lesson-number" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="lesson-title">{item.title}</span>
              </button>
            )
          })}
          <p className="lesson-note">Progress is kept only while this tab stays open.</p>
        </nav>

        <article className="lesson">
          <div className="lesson-head">
            <p className="lesson-count">
              Lesson {lessonIndex + 1} of {LESSONS.length}
              {lesson.steps.length > 1 && `, part ${stepIndex + 1} of ${lesson.steps.length}`}
            </p>
            <h1>{lesson.title}</h1>
            <p className="lesson-text">{lesson.text}</p>
          </div>

          <div className={`task ${solved ? 'is-solved' : ''}`} aria-live="polite">
            {solved ? (
              <>
                <strong>Done.</strong> {step.done}
              </>
            ) : (
              <>
                <strong>Your turn.</strong> {step.task}
              </>
            )}
            {nudge && <span className="task-nudge">{nudge}</span>}
            {error && <span className="task-nudge">{error}</span>}
          </div>

          <div className="lesson-board">
            <div className="lesson-stage">
              <div className="layer-picker" role="group" aria-label="Current layer">
              {LAYERS.filter((layer) => BOARD_LAYERS.includes(layer.z)).map((layer) => (
                <button
                  key={layer.z}
                  type="button"
                  className={`button layer-button ${activeLayer === layer.z ? 'is-selected' : ''}`}
                  aria-pressed={activeLayer === layer.z}
                  style={activeLayer === layer.z ? { background: layer.light, borderColor: layer.light } : undefined}
                  onClick={() => setActiveLayer(layer.z)}
                >
                  <i className="swatch" style={{ background: layer.dark }} />
                  {layer.name}
                </button>
              ))}
              </div>
              <div className="board-frame">
                <CubeBoard
                  board={board}
                  size={BOARD.size}
                  layers={BOARD_LAYERS}
                  activeLayer={activeLayer}
                  selected={selected}
                  legalMoves={legalMoves}
                  goal={showGoal ? step.to : null}
                  onCellClick={onCellClick}
                />
              </div>
            </div>

            <aside className="lesson-side">
              <h2>{layerOf(activeLayer).name}, seen from above</h2>
              <LayerMap
                board={board}
                size={BOARD.size}
                z={activeLayer}
                side="white"
                selected={selected}
                legalMoves={legalMoves}
                goal={showGoal ? step.to : null}
                onCellClick={onCellClick}
              />
              <ul className="legend">
                <li>
                  <span className="map-dot legend-dot" />A cell the piece can reach
                </li>
                <li>
                  <span className="legend-goal" />
                  Where this task wants it
                </li>
                <li>
                  <span className="legend-capture" />A piece it can capture
                </li>
              </ul>
            </aside>
          </div>

          <div className="lesson-actions">
            <button
              type="button"
              className="button"
              disabled={lessonIndex === 0 && stepIndex === 0}
              onClick={() => (stepIndex > 0 ? setStepIndex(stepIndex - 1) : open(lessonIndex - 1))}
            >
              Previous
            </button>
            <button type="button" className="button" disabled={solved} onClick={showMe}>
              Show me
            </button>
            <button type="button" className="button" onClick={() => lay(step)}>
              Reset board
            </button>
            {lastStep && lastLesson ? (
              <a className={`button button-primary ${solved ? '' : 'is-waiting'}`} href="#/setup" aria-disabled={!solved}>
                Play a game
              </a>
            ) : (
              <button type="button" className="button button-primary" disabled={!solved} onClick={next}>
                {lastStep ? 'Next lesson' : 'Next part'}
              </button>
            )}
            {!solved && <span className="lesson-wait">Make the move to continue.</span>}
          </div>
        </article>
      </main>
    </div>
  )
}
