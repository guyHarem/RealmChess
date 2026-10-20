// The lobby: open online games waiting for players, to join with one click, or a new one
// opened with your usual settings to wait here for someone else
import { useEffect, useState } from 'react'
import FeedbackButton from '../components/Feedback.jsx'
import Logo from '../components/Logo.jsx'
import { OFFLINE, fetchLobby, openGame, track } from '../lib/api.js'
import { navigate } from '../lib/router.js'
import { clockRequest, cloudRequest, dynamiteRequest, levelName, loadSettings, portalRequest, saveSettings } from '../lib/settings.js'

const POLL_MS = 3000
const NAMES = { white: 'White', black: 'Black' }

function clockText(clock) {
  if (!clock) return 'No clock'
  const minutes = clock.initial / 60
  return `${Number.isInteger(minutes) ? minutes : minutes.toFixed(1)} min${clock.increment ? ` + ${clock.increment} s` : ''}`
}

function waitingText(seconds) {
  if (seconds < 60) return 'just opened'
  const minutes = Math.floor(seconds / 60)
  return `waiting ${minutes} min`
}

// What is special about a game, in a few words
function rulesOf(game) {
  return [
    clockText(game.clock),
    game.rocks ? null : 'no rocks',
    game.portals ? 'portals' : null,
    game.dynamite ? 'dynamite' : null,
    game.clouds ? 'clouds' : null,
  ].filter(Boolean)
}

export default function Lobby() {
  const [lobby, setLobby] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let stopped = false
    let timer = null
    async function load() {
      try {
        const data = await fetchLobby()
        if (stopped) return
        if (data.success) {
          setLobby(data)
          setError(null)
        }
      } catch {
        if (!stopped) setError(OFFLINE)
      }
      if (!stopped) timer = setTimeout(load, POLL_MS)
    }
    load()
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [])

  function join(game, side) {
    track({ event: 'lobby_join' })
    navigate(`/game/${game.id}${game.teams ? `/${side}` : ''}`)
  }

  // Your usual rules (from the setup page), as an open game against anyone
  async function openOne() {
    setBusy(true)
    const settings = loadSettings()
    const side = Math.random() < 0.5 ? 'white' : 'black'
    try {
      const data = await openGame({
        kind: 'online',
        public: true,
        side,
        rocks: settings.rocks,
        move_limit: Number(settings.moveLimit) || 50,
        clock: clockRequest(settings.clock),
        portals: portalRequest(settings),
        dynamite: dynamiteRequest(settings),
        clouds: cloudRequest(settings),
      })
      if (!data.success) throw new Error(data.error)
      navigate(`/game/${data.game_id}`)
    } catch (problem) {
      setError(problem instanceof TypeError || problem instanceof SyntaxError ? OFFLINE : problem.message)
      setBusy(false)
    }
  }

  // Play now: the game that has waited longest for one opponent, or else a new one of your own
  function playNow() {
    track({ event: 'quick_play' })
    const waiting = lobby?.games.find((game) => !game.teams && !game.computer)
    if (waiting) join(waiting, waiting.free[0])
    else openOne()
  }

  // Choose the rules first on the setup page
  function chooseRules() {
    saveSettings({ ...loadSettings(), opponent: 'online', openGame: true })
    navigate('/setup')
  }

  const games = lobby?.games ?? []

  return (
    <div className="page">
      <header className="bar">
        <Logo />
        <div className="bar-links">
          <FeedbackButton />
          <a className="bar-link" href="#/">
            Back to home
          </a>
        </div>
      </header>

      <main className="lobby-main">
        <div className="lobby-head">
          <h1>Play anyone</h1>
          <p>Join a game that is waiting for a player, or open your own and wait here for someone to join.</p>
          <div className="lobby-actions">
            <button type="button" className="button button-primary button-large" disabled={busy || !lobby} onClick={playNow}>
              {busy ? 'Opening' : 'Play now'}
            </button>
            <button type="button" className="button button-large" disabled={busy} onClick={chooseRules}>
              Open a game with my rules
            </button>
          </div>
          <p className="help">
            Play now joins the game that has waited longest, or opens one with the rules you last used. Players in open games
            talk with a few set phrases.
          </p>
        </div>

        {error && <p className="banner-error">{error}</p>}

        <section className="lobby-list" aria-label="Open games">
          <h2>
            Open games
            {lobby && <small>{lobby.playing === 1 ? '1 game being played online now' : `${lobby.playing} games being played online now`}</small>}
          </h2>
          {!lobby && !error && <p className="lobby-empty">Looking for games…</p>}
          {lobby && games.length === 0 && (
            <p className="lobby-empty">No open games right now. Open one, and it waits here for an opponent.</p>
          )}
          {games.map((game) => (
            <article key={game.id} className="lobby-game">
              <div className="lobby-game-text">
                <strong>
                  {game.teams
                    ? game.computer
                      ? `A team against the computer, ${levelName(game.computer)}`
                      : `Teams of two, ${game.players} of 4 seated`
                    : 'One against one'}
                </strong>
                <span>
                  {rulesOf(game).join(' · ')} · {game.moves > 0 ? 'in progress' : waitingText(game.waiting)}
                </span>
              </div>
              <div className="lobby-game-seats">
                {game.free.map((side) => (
                  <button key={side} type="button" className="button" onClick={() => join(game, side)}>
                    <i className={`chip chip-${side}`} />
                    {game.teams ? `Join ${NAMES[side]}` : `Play ${NAMES[side]}`}
                  </button>
                ))}
              </div>
            </article>
          ))}
        </section>
      </main>
    </div>
  )
}
