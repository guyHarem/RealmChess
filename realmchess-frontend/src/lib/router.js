// Minimal hash router: #/, #/setup, #/game, ...
import { useEffect, useState } from 'react'

const current = () => window.location.hash.replace(/^#/, '') || '/'

export function useRoute() {
  const [route, setRoute] = useState(current)
  useEffect(() => {
    const onChange = () => setRoute(current())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export function navigate(path) {
  window.location.hash = path
}
