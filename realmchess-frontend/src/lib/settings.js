// Game setup choices, remembered in this browser between visits

export const DEFAULT_SETTINGS = {
  opponent: 'local', // 'local' (two players on this screen), 'computer' or 'online'
  teams: false, // two players a side, taking turns with the army
  onlineRival: 'friends', // a team online plays 'friends' (another team) or the 'computer'
  openGame: false, // an online game open to anyone (listed in the lobby), not just a friend with the link
  level: 'medium', // the computer's level
  side: 'white', // which colour sits nearest the camera; against the computer, the side you play
  rocks: true,
  portals: 'off', // 'off', 'classic' (the designed layout) or 'shuffle' (random, mirrored)
  dynamite: 'off', // the same three choices
  clouds: 'off', // the same three choices
  showLegalMoves: true,
  allowUndo: true,
  sound: true,
  moveLimit: 50,
  clock: { mode: 'none', minutes: 10, increment: 0 }, // minutes and increment are used by mode 'custom'
}

export const CLOCK_PRESETS = [
  { mode: 'none', label: 'No clock' },
  { mode: '5', label: '5 min', initial: 300, increment: 0 },
  { mode: '10', label: '10 min', initial: 600, increment: 0 },
  { mode: '10+3', label: '10 min + 3 s', initial: 600, increment: 3 },
  { mode: 'custom', label: 'Custom' },
]

export const LEVELS = [
  { id: 'easy', label: 'Easy', hint: 'It looks one move ahead' },
  { id: 'medium', label: 'Medium', hint: 'It looks two moves ahead' },
  { id: 'hard', label: 'Hard', hint: 'It thinks for about 3 seconds a move' },
]
export const levelName = (id) => LEVELS.find((level) => level.id === id)?.label ?? id

// Whether the computer plays: against it on this screen, or a team playing it online
export const playsComputer = (settings) =>
  settings.opponent === 'computer' || (settings.opponent === 'online' && settings.teams && settings.onlineRival === 'computer')

// The computer part of a "new game" request: null for two players, else its colour and level
export function computerRequest(settings, side = settings.side) {
  if (!playsComputer(settings)) return null
  return { color: side === 'white' ? 'black' : 'white', level: settings.level }
}

export const PORTAL_CHOICES = [ // also the dynamite choices
  { id: 'off', label: 'Off' },
  { id: 'classic', label: 'Classic' },
  { id: 'shuffle', label: 'Shuffle' },
]

// The portal and dynamite parts of a "new game" request
export const portalRequest = (settings) => (settings.portals === 'off' ? undefined : settings.portals)
export const dynamiteRequest = (settings) => (settings.dynamite === 'off' ? undefined : settings.dynamite)
export const cloudRequest = (settings) => (settings.clouds === 'off' ? undefined : settings.clouds)

// The clock part of a "new game" request: null for no clock, else seconds
export function clockRequest(clock) {
  if (!clock || clock.mode === 'none') return null
  if (clock.mode === 'custom') {
    return { initial: Math.round(Number(clock.minutes) * 60), increment: Math.round(Number(clock.increment)) }
  }
  const preset = CLOCK_PRESETS.find((option) => option.mode === clock.mode)
  return preset ? { initial: preset.initial, increment: preset.increment } : null
}

const KEY = 'realmchess.settings'

export function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(KEY) ?? sessionStorage.getItem(KEY) ?? '{}') }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(settings) {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    // Storage can be unavailable (private windows); the game still works with defaults
  }
}
