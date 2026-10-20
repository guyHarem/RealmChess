// Short sounds for the game, made on the spot with the Web Audio API (no sound files).
// Browsers only allow sound after the visitor has clicked or tapped the page; until then
// these stay silent.

let context = null

function audio() {
  if (!context) {
    const Context = window.AudioContext ?? window.webkitAudioContext
    if (!Context) return null
    context = new Context()
  }
  if (context.state === 'suspended') context.resume()
  return context
}

// One soft note: a sine (or triangle) that starts at `frequency` and fades out
function note(ctx, { frequency, start = 0, length = 0.12, volume = 0.18, type = 'sine', slide = 1 }) {
  const at = ctx.currentTime + start
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.type = type
  oscillator.frequency.setValueAtTime(frequency, at)
  oscillator.frequency.exponentialRampToValueAtTime(frequency * slide, at + length)
  gain.gain.setValueAtTime(0.0001, at)
  gain.gain.exponentialRampToValueAtTime(volume, at + 0.008)
  gain.gain.exponentialRampToValueAtTime(0.0001, at + length)
  oscillator.connect(gain).connect(ctx.destination)
  oscillator.start(at)
  oscillator.stop(at + length + 0.02)
}

// A short burst of noise falling in pitch: the dynamite going off
function boom(ctx) {
  const length = 0.7
  const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * length), ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 2
  const source = ctx.createBufferSource()
  source.buffer = buffer
  const filter = ctx.createBiquadFilter()
  filter.type = 'lowpass'
  const at = ctx.currentTime + 0.3 // as the mover lands
  filter.frequency.setValueAtTime(1800, at)
  filter.frequency.exponentialRampToValueAtTime(120, at + length)
  const gain = ctx.createGain()
  gain.gain.value = 0.5
  source.connect(filter).connect(gain).connect(ctx.destination)
  source.start(at)
  note(ctx, { frequency: 90, start: 0.3, length: 0.5, slide: 0.5, volume: 0.3 })
}

const SOUNDS = {
  blast: boom,
  move: (ctx) => note(ctx, { frequency: 520, length: 0.09, type: 'triangle', slide: 0.7 }),
  capture: (ctx) => {
    note(ctx, { frequency: 300, length: 0.16, type: 'triangle', slide: 0.5, volume: 0.24 })
    note(ctx, { frequency: 760, start: 0.02, length: 0.08, slide: 0.6, volume: 0.1 })
  },
  check: (ctx) => {
    note(ctx, { frequency: 660, length: 0.1, type: 'triangle' })
    note(ctx, { frequency: 880, start: 0.11, length: 0.14, type: 'triangle' })
  },
  end: (ctx) => {
    for (const [i, frequency] of [523, 659, 784].entries()) note(ctx, { frequency, start: i * 0.09, length: 0.4, volume: 0.12 })
  },
}

export function playSound(name) {
  try {
    const ctx = audio()
    if (ctx) SOUNDS[name]?.(ctx)
  } catch {
    // Sound is a nicety: never let it get in the way of the game
  }
}
