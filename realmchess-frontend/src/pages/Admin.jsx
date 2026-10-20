// The admin page (#/admin): what is going on now, the anonymous play counts per day, and the
// players' feedback. The server asks for the admin key (REALMCHESS_ADMIN_KEY on the host).
import { useCallback, useEffect, useState } from 'react'
import Logo from '../components/Logo.jsx'
import { adminKey, fetchAdmin, markFeedback, rememberAdminKey } from '../lib/api.js'

const REFRESH_MS = 15000
const PERIODS = [
  { id: 1, label: 'Today' },
  { id: 7, label: '7 days' },
  { id: 30, label: '30 days' },
  { id: 180, label: 'All' },
]
const KIND_NAMES = { bug: 'Problem', idea: 'Idea', other: 'Other' }

// Add up the counts of the last `days` days (the newest day is today)
function total(days, count) {
  const sum = {}
  for (const day of Object.keys(days).sort().slice(-count)) {
    for (const [name, n] of Object.entries(days[day])) sum[name] = (sum[name] ?? 0) + n
  }
  return sum
}

const percent = (part, whole) => (whole ? `${Math.round((100 * part) / whole)}%` : '–')

function when(seconds) {
  return new Date(seconds * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

function lasting(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours >= 24 ? `${Math.floor(hours / 24)} d ${hours % 24} h` : hours ? `${hours} h ${minutes} min` : `${minutes} min`
}

function Tile({ label, value, note }) {
  return (
    <div className="admin-tile">
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  )
}

// A small table of names and counts, biggest first, with each one's share of `whole`
function Breakdown({ title, rows, whole }) {
  const shown = rows.filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1])
  return (
    <section className="admin-card">
      <h3>{title}</h3>
      {shown.length === 0 ? (
        <p className="admin-none">Nothing yet.</p>
      ) : (
        <table>
          <tbody>
            {shown.map(([name, n]) => (
              <tr key={name}>
                <th scope="row">{name}</th>
                <td>{n}</td>
                {whole !== undefined && <td className="admin-share">{percent(n, whole)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

// Visitors and games started, one pair of bars a day for the last 30 days
function DailyChart({ days }) {
  const list = []
  const today = new Date()
  for (let back = 29; back >= 0; back--) {
    const day = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - back)).toISOString().slice(0, 10)
    list.push({ day, visitors: days[day]?.visitors ?? 0, games: days[day]?.['games.started'] ?? 0 })
  }
  const top = Math.max(1, ...list.map((entry) => Math.max(entry.visitors, entry.games)))
  return (
    <section className="admin-card admin-chart-card">
      <h3>
        The last 30 days
        <span className="admin-legend">
          <i className="admin-key-visitors" /> visitors <i className="admin-key-games" /> games started
        </span>
      </h3>
      <div className="admin-chart" role="img" aria-label="Visitors and games started per day, for the last 30 days">
        {list.map((entry) => (
          <div key={entry.day} className="admin-day" title={`${entry.day}: ${entry.visitors} visitors, ${entry.games} games`}>
            <span className="admin-bar admin-bar-visitors" style={{ height: `${(100 * entry.visitors) / top}%` }} />
            <span className="admin-bar admin-bar-games" style={{ height: `${(100 * entry.games) / top}%` }} />
          </div>
        ))}
      </div>
      <div className="admin-chart-axis">
        <span>{list[0].day.slice(5)}</span>
        <span>today</span>
      </div>
    </section>
  )
}

export default function Admin() {
  const [data, setData] = useState(null)
  const [locked, setLocked] = useState(false)
  const [error, setError] = useState(null)
  const [key, setKey] = useState('')
  const [period, setPeriod] = useState(7)
  const [showHandled, setShowHandled] = useState(false)

  const load = useCallback(async () => {
    try {
      const answer = await fetchAdmin()
      if (answer.success) {
        setData(answer)
        setLocked(false)
        setError(null)
      } else {
        setLocked(true)
        setError(adminKey() ? answer.error : null)
      }
    } catch {
      setError('Cannot reach the server.')
    }
  }, [])

  useEffect(() => {
    let timer = null
    const tick = async () => {
      await load()
      timer = setTimeout(tick, REFRESH_MS)
    }
    tick()
    return () => clearTimeout(timer)
  }, [load])

  async function unlock(event) {
    event.preventDefault()
    rememberAdminKey(key.trim())
    setKey('')
    await load()
  }

  async function mark(id, done) {
    const answer = await markFeedback(id, done)
    if (answer.success) setData((current) => ({ ...current, feedback: answer.feedback }))
  }

  if (locked || !data) {
    return (
      <div className="page">
        <header className="bar">
          <Logo />
        </header>
        <main className="admin-lock">
          <h1>Admin</h1>
          {locked ? (
            <form onSubmit={unlock}>
              <label htmlFor="admin-key">Admin key</label>
              <input id="admin-key" type="password" autoComplete="current-password" value={key} onChange={(event) => setKey(event.target.value)} />
              <button type="submit" className="button button-primary" disabled={!key.trim()}>
                Open
              </button>
              <p className="help">The key is REALMCHESS_ADMIN_KEY, on the service's Environment page in the Render dashboard.</p>
            </form>
          ) : (
            <p>{error ?? 'Loading…'}</p>
          )}
          {locked && error && <p className="banner-error">{error}</p>}
        </main>
      </div>
    )
  }

  const { live, days, feedback, server } = data
  const sum = total(days, period)
  const started = sum['games.started'] ?? 0
  const finished = sum['games.finished'] ?? 0
  const get = (name) => sum[name] ?? 0
  const prefixed = (prefix, names) => Object.entries(names).map(([id, label]) => [label, get(prefix + id)])
  const levels = ['easy', 'medium', 'hard'].map((level) => {
    const won = get(`computer.${level}.won`)
    const lost = get(`computer.${level}.lost`)
    const drew = get(`computer.${level}.drew`)
    return { level, won, lost, drew, played: won + lost + drew, started: get(`games.level.${level}`) }
  })
  const openFeedback = feedback.filter((item) => !item.done)
  const shownFeedback = [...(showHandled ? feedback : openFeedback)].reverse()

  return (
    <div className="page admin">
      <header className="bar">
        <Logo />
        <div className="bar-links">
          <button type="button" className="bar-link link-plain" onClick={load}>
            Refresh
          </button>
          <a className="bar-link" href="#/">
            Back to home
          </a>
        </div>
      </header>

      <main className="admin-main">
        <section>
          <h2>Right now</h2>
          <div className="admin-tiles">
            <Tile label="Games being played" value={live.playing} note="moved in the last minute" />
            <Tile label="Online games" value={live.online_playing} />
            <Tile label="Players connected" value={live.players_connected} note="online games" />
            <Tile label="Open games in the lobby" value={live.open_games} />
            <Tile label="Games in memory" value={live.rooms} note="kept a day after the last move" />
          </div>
        </section>

        <section>
          <div className="admin-period">
            <h2>Play counts</h2>
            <div className="choices" role="group" aria-label="Period">
              {PERIODS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className={`choice ${period === option.id ? 'is-selected' : ''}`}
                  aria-pressed={period === option.id}
                  onClick={() => setPeriod(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          <div className="admin-tiles">
            <Tile label="Visitors" value={get('visitors')} note={period > 1 ? 'each counted once a day' : 'counted once a day'} />
            <Tile label="Games started" value={started} />
            <Tile label="Games finished" value={finished} note={`${percent(finished, started)} of started`} />
            <Tile label="Average length" value={finished ? Math.round(get('games.plies') / finished / 2) : '–'} note="moves each, finished games" />
            <Tile label="Lessons finished" value={get('event.lesson_done')} />
            <Tile label="Puzzles solved" value={get('event.puzzle_solved')} />
            <Tile label="Feedback" value={get('feedback')} note={`${openFeedback.length} not handled`} />
          </div>
        </section>

        <DailyChart days={days} />

        <div className="admin-grid">
          <Breakdown
            title="Kinds of game"
            whole={started}
            rows={[
              ...prefixed('games.kind.', { local: 'Two on one screen', computer: 'Against the computer', online: 'Online with a friend', open: 'Open (lobby)' }),
              ['Teams of two (any kind)', get('games.teams')],
              ['With a clock', get('games.clock')],
              ['Without rocks', get('games.no_rocks')],
            ]}
          />
          <Breakdown
            title="Special cells"
            whole={started}
            rows={[
              ...prefixed('games.portals.', { classic: 'Portals, classic', shuffle: 'Portals, shuffled' }),
              ...prefixed('games.dynamite.', { classic: 'Dynamite, classic', shuffle: 'Dynamite, shuffled' }),
              ...prefixed('games.clouds.', { classic: 'Clouds, classic', shuffle: 'Clouds, shuffled' }),
            ]}
          />
          <section className="admin-card">
            <h3>Against the computer</h3>
            <table>
              <thead>
                <tr>
                  <th scope="col">Level</th>
                  <th scope="col">Started</th>
                  <th scope="col">Player won</th>
                  <th scope="col">Drew</th>
                  <th scope="col">Lost</th>
                </tr>
              </thead>
              <tbody>
                {levels.map((row) => (
                  <tr key={row.level}>
                    <th scope="row">{row.level[0].toUpperCase() + row.level.slice(1)}</th>
                    <td>{row.started}</td>
                    <td>{percent(row.won, row.played)}</td>
                    <td>{percent(row.drew, row.played)}</td>
                    <td>{percent(row.lost, row.played)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="admin-none">Of the finished games at each level.</p>
          </section>
          <Breakdown
            title="How games ended"
            whole={finished}
            rows={prefixed('games.ending.', {
              checkmate: 'Checkmate',
              resigned: 'Resigned',
              abandoned: 'Opponent left',
              timeout: 'Out of time',
              agreed_draw: 'Agreed draw',
              stalemate: 'Stalemate',
              repetition: 'Repetition',
              move_limit: 'Quiet-move limit',
              insufficient_material: 'Too few pieces',
            })}
          />
          <Breakdown
            title="Winners (between people)"
            rows={prefixed('games.winner.', { white: 'White', black: 'Black', draw: 'Draw' })}
          />
          <Breakdown
            title="Pages opened"
            rows={prefixed('page.', { home: 'Home', setup: 'Setup', game: 'Game', lobby: 'Lobby', learn: 'Lessons', scenarios: 'Puzzles' })}
          />
          <Breakdown
            title="Online"
            rows={[
              ['Friends joined by link', get('online.joined')],
              ['Strangers joined from the lobby', get('lobby.joined')],
              ['Play now pressed', get('event.quick_play')],
              ['Messages to the team', get('chat.team')],
              ['Messages to everyone', get('chat.all')],
              ['Hints asked for', get('hints')],
              ['Games never finished', get('games.abandoned')],
            ]}
          />
        </div>

        <section className="admin-feedback">
          <div className="admin-period">
            <h2>Feedback</h2>
            <label className="admin-check">
              <input type="checkbox" checked={showHandled} onChange={(event) => setShowHandled(event.target.checked)} />
              Show handled too
            </label>
          </div>
          {shownFeedback.length === 0 && <p className="admin-none">{showHandled ? 'No feedback yet.' : 'Nothing waiting.'}</p>}
          {shownFeedback.map((item) => (
            <article key={item.id} className={`admin-message ${item.done ? 'is-done' : ''}`}>
              <div className="admin-message-head">
                <span className={`admin-tag admin-tag-${item.kind}`}>{KIND_NAMES[item.kind] ?? item.kind}</span>
                <span>{when(item.at)}</span>
                <button type="button" className="button" onClick={() => mark(item.id, !item.done)}>
                  {item.done ? 'Reopen' : 'Mark handled'}
                </button>
              </div>
              <p className="admin-message-text">{item.text}</p>
              <p className="admin-message-meta">
                {item.contact && <span>From: {item.contact}</span>}
                {item.page && <span>Page: {item.page}</span>}
                {item.game && <span>Game: {item.game}</span>}
                {item.agent && <span title={item.agent}>{item.agent.slice(0, 80)}</span>}
              </p>
            </article>
          ))}
        </section>

        <section className="admin-server">
          <h2>Server</h2>
          <p>
            Running since {when(server.started)} ({lasting(server.now - server.started)}). Version {server.commit ?? 'local'}.{' '}
            {server.handoff
              ? `Took over ${server.taken_over.pulled + server.taken_over.pushed} game(s) at the last deploy.`
              : 'No handoff key: a deploy ends the games and resets these counts.'}{' '}
            Counts and feedback live in memory and move to the new server on a deploy; a crash loses them (feedback is also in
            the server log).
          </p>
        </section>
      </main>
    </div>
  )
}
