import { useEffect, useState } from 'react'
import CubeBoard from '../components/CubeBoard.jsx'
import FeedbackButton from '../components/Feedback.jsx'
import { LogoMark } from '../components/Logo.jsx'
import { fetchLobby } from '../lib/api.js'
import { LESSON_BOARD, LESSON_MOVES, PUZZLE_BOARD, SMALL_BOARD, START_BOARD } from '../lib/chess.js'
import { LESSONS, PUZZLES, clearProgress, loadIds } from '../lib/progress.js'
import course from '../lessons.json'

export default function Home() {
  const [started, setStarted] = useState(() => loadIds(LESSONS).length + loadIds(PUZZLES).length > 0)
  const [waiting, setWaiting] = useState(null) // open games in the lobby, once known

  useEffect(() => {
    let stopped = false
    fetchLobby()
      .then((data) => !stopped && data.success && setWaiting(data.games.length))
      .catch(() => {})
    return () => {
      stopped = true
    }
  }, [])
  return (
    <div className="page home">
      <main className="home-main">
        <div className="home-title">
          <div className="home-brand">
            <LogoMark size={84} />
            <h1>
              Realm<span>Chess</span>
            </h1>
          </div>
          <p>Chess on five stacked boards. Climb to the sky or drop into the dungeon.</p>
        </div>

        <div className="modes">
          <a className="mode mode-learn" href="#/learn">
            <div className="mode-picture">
              <CubeBoard
                interactive={false}
                board={LESSON_BOARD}
                size={SMALL_BOARD.size}
                layers={SMALL_BOARD.layers}
                selected={[2, 2, 0]}
                legalMoves={LESSON_MOVES}
                goal={[2, 4, 1]}
              />
            </div>
            <h2>Learn How to Play</h2>
            <p>{course.lessons.length} short lessons. Try every move yourself.</p>
            <span className="button">Start learning</span>
          </a>

          <a className="mode mode-play" href="#/setup">
            <div className="mode-picture">
              <CubeBoard interactive={false} board={START_BOARD} />
            </div>
            <h2>Play RealmChess</h2>
            <p>Play the computer, a friend beside you, or a friend online with a link.</p>
            <span className="button button-primary">Set up a game</span>
          </a>

          <a className="mode mode-scenarios" href="#/scenarios">
            <div className="mode-picture">
              <CubeBoard interactive={false} board={PUZZLE_BOARD} />
            </div>
            <h2>Play Scenarios</h2>
            <p>Solve set positions. They start easy and get harder.</p>
            <span className="button">Open scenarios</span>
          </a>
        </div>

        <a className="home-lobby" href="#/lobby">
          <span>
            <strong>Play anyone online</strong>
            {waiting === null
              ? 'Join an open game, or open one and wait for an opponent.'
              : waiting === 0
                ? 'No open games right now: open one, and someone can join it.'
                : waiting === 1
                  ? '1 open game is waiting for a player.'
                  : `${waiting} open games are waiting for players.`}
          </span>
          <span className="button">Find an opponent</span>
        </a>

        <p className="home-note">
          {started
            ? 'This browser remembers the lessons and puzzles you finish. '
            : 'This browser will remember the lessons and puzzles you finish. '}
          {started && (
            <button
              type="button"
              className="link-button"
              onClick={() => {
                clearProgress()
                setStarted(false)
              }}
            >
              Start over
            </button>
          )}{' '}
          <FeedbackButton className="link-button" />
        </p>
      </main>
    </div>
  )
}
