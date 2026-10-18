import CubeBoard from '../components/CubeBoard.jsx'
import { LogoMark } from '../components/Logo.jsx'
import { LESSON_BOARD, LESSON_MOVES, PUZZLE_BOARD, SMALL_BOARD, START_BOARD } from '../lib/chess.js'

export default function Home() {
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
            <p>Nine short lessons on a small board. Try every move yourself.</p>
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

        <p className="home-note">Progress is not saved yet. It resets when you close the page.</p>
      </main>
    </div>
  )
}
