// One player's countdown. The server owns the time; between its answers the
// running clock counts down locally so the display stays smooth.
import { useEffect, useState } from 'react'

function format(seconds) {
  const whole = Math.ceil(seconds)
  const hours = Math.floor(whole / 3600)
  const minutes = Math.floor((whole % 3600) / 60)
  const rest = String(whole % 60).padStart(2, '0')
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

export default function Clock({ clock, color, receivedAt, onFlag }) {
  const running = clock.running === color
  const [now, setNow] = useState(receivedAt)

  useEffect(() => {
    if (!running) return undefined
    const timer = setInterval(() => setNow(performance.now()), 200)
    return () => clearInterval(timer)
  }, [running])

  const elapsed = running ? Math.max(0, now - receivedAt) / 1000 : 0
  const left = Math.max(0, clock[color] - elapsed)
  const flagged = running && left <= 0

  // Out of time on our side: ask the server, which decides the result
  useEffect(() => {
    if (flagged) onFlag?.()
  }, [flagged, onFlag])

  return (
    <span className={`clock ${running ? 'is-running' : ''} ${left < 30 ? 'is-low' : ''}`} role="timer" aria-label={`${color} clock`}>
      {format(left)}
    </span>
  )
}
