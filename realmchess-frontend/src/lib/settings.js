// Game setup choices. Kept for the browser tab only: nothing is saved between visits yet.

export const DEFAULT_SETTINGS = {
  opponent: 'local', // 'local' (two players on this screen), 'computer' or 'online'
  level: 'medium', // the computer's level
  side: 'white', // which colour sits nearest the camera; against the computer, the side you play
  rocks: true,
  showLegalMoves: true,
  allowUndo: true,
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

// The computer part of a "new game" request: null for two players, else its colour and level
export function computerRequest(settings, side = settings.side) {
  if (settings.opponent !== 'computer') return null
  return { color: side === 'white' ? 'black' : 'white', level: settings.level }
}

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
    return { ...DEFAULT_SETTINGS, ...JSON.parse(sessionStorage.getItem(KEY) ?? '{}') }
  } catch {
    return { ...DEFAULT_SETTINGS }
  }
}

export function saveSettings(settings) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(settings))
  } catch {
    // Storage can be unavailable (private windows); the game still works with defaults
  }
}
