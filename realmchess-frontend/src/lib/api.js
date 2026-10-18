// Thin wrapper over the Flask API. Vite proxies /api to the backend in development.
//
// Every game lives in its own room on the server: openGame() makes one and answers with its
// id, and every later call names that id. Lessons and scenarios pass 'practice' instead and
// get a scratch room of their own for this tab.

// What to say when the server does not answer. Visitors of the hosted game cannot start
// anything; on a developer's machine the usual cause is that the backend is not running.
export const OFFLINE = import.meta.env.DEV
  ? 'Cannot reach the game server. Start it with: python api/app.py'
  : 'Cannot reach the game server. Check your connection and try again in a moment.'

const SEAT = 'realmchess.seat.' // + room id: the secret key that says which side of an online game is ours
const PRACTICE = 'realmchess.practice'
const LAST_GAME = 'realmchess.game'

function read(store, key) {
  try {
    return store.getItem(key)
  } catch {
    return null // storage can be unavailable (private windows); the game still works for this visit
  }
}

function write(store, key, value) {
  try {
    store.setItem(key, value)
  } catch {
    // see read()
  }
}

// A seat key is kept across visits, so reopening the link puts you back on your side
export const seatOf = (game) => read(localStorage, SEAT + game)
export const rememberSeat = (game, seat) => write(localStorage, SEAT + game, seat)
export const lastGame = () => read(sessionStorage, LAST_GAME)

function url(path, game) {
  if (!game || game === 'main') return '/api' + path
  return '/api' + path + (path.includes('?') ? '&' : '?') + 'game=' + encodeURIComponent(game)
}

async function send(path, body, game) {
  const options = body === undefined ? { headers: {} } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
  const seat = game && seatOf(game)
  if (seat) options.headers['X-Seat'] = seat
  const response = await fetch(url(path, game), options)
  return response.json()
}

// Open a room and start a game in it: { kind: 'local' | 'computer' | 'online' | 'practice', ...options }
export async function openGame(options) {
  const data = await send('/games', options)
  if (data.success) {
    if (data.seat) rememberSeat(data.game_id, data.seat)
    if (options.kind !== 'practice') write(sessionStorage, LAST_GAME, data.game_id)
  }
  return data
}

let practice = null // a promise of this tab's scratch room id, once asked for
let practiceId = null // ... and the id itself once it is known

function practiceRoom(staleId) {
  // Several calls can find the room gone at once: only the first of them replaces it
  const replace = staleId !== undefined && practiceId === staleId
  if (!practice || replace) {
    practiceId = null
    practice = (async () => {
      let id = !replace && read(sessionStorage, PRACTICE)
      if (!id) {
        id = (await send('/games', { kind: 'practice' })).game_id
        write(sessionStorage, PRACTICE, id)
      }
      practiceId = id
      return id
    })()
  }
  return practice
}

export async function api(path, body, game) {
  if (game !== 'practice') return send(path, body, game)
  const room = await practiceRoom()
  let data = await send(path, body, room)
  // The server forgets rooms after a day, or when it restarts: quietly start a new one
  if (data.gone) data = await send(path, body, await practiceRoom(room))
  return data
}

export const legalMovesOf = (coord, game) =>
  api('/game/legal-moves?from=' + encodeURIComponent(JSON.stringify(coord)), undefined, game)
