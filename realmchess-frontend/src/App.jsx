import { lazy, Suspense, useEffect } from 'react'
import { lastGame, track } from './lib/api.js'
import { useRoute } from './lib/router.js'
import Game from './pages/Game.jsx'
import Home from './pages/Home.jsx'
import Learn from './pages/Learn.jsx'
import Lobby from './pages/Lobby.jsx'
import Scenarios from './pages/Scenarios.jsx'
import Setup from './pages/Setup.jsx'
import './app.css'

// Developer tool for poking at backend behaviour: only on a developer's machine, and left
// out of the build that visitors get
const TestBench = import.meta.env.DEV ? lazy(() => import('./bench/TestBench.jsx')) : null
// Play counts and feedback, for whoever has the admin key: loaded only when opened
const Admin = lazy(() => import('./pages/Admin.jsx'))

// The page a route shows, for the anonymous page counts
const PAGE_OF = { '/': 'home', '/setup': 'setup', '/learn': 'learn', '/lobby': 'lobby' }
const pageOf = (route) => PAGE_OF[route] ?? (route.startsWith('/game') ? 'game' : route.startsWith('/scenarios') ? 'scenarios' : null)

export default function App() {
  const route = useRoute()
  const page = pageOf(route)

  useEffect(() => {
    if (page) track({ page })
  }, [page])

  if (route === '/setup') return <Setup />
  if (route.startsWith('/game')) {
    // Every game has its own address; a bare #/game goes back to the one last played here
    // #/game/<id>, or #/game/<id>/<side> from an invite to play that side of a team game
    const [, , linkId, side] = route.split('/')
    const id = linkId ?? lastGame()
    if (!id) return <Setup />
    return <Game key={id} id={id} joinSide={side === 'white' || side === 'black' ? side : null} />
  }
  if (route === '/learn') return <Learn />
  if (route === '/lobby') return <Lobby />
  if (route.startsWith('/scenarios')) return <Scenarios id={route.split('/')[2]} />
  if (route === '/admin') {
    return (
      <Suspense fallback={null}>
        <Admin />
      </Suspense>
    )
  }
  if (TestBench && route === '/bench') {
    return (
      <Suspense fallback={null}>
        <TestBench />
      </Suspense>
    )
  }
  return <Home />
}
