import { lazy, Suspense } from 'react'
import { lastGame } from './lib/api.js'
import { useRoute } from './lib/router.js'
import Game from './pages/Game.jsx'
import Home from './pages/Home.jsx'
import Learn from './pages/Learn.jsx'
import Scenarios from './pages/Scenarios.jsx'
import Setup from './pages/Setup.jsx'
import './app.css'

// Developer tool for poking at backend behaviour: only on a developer's machine, and left
// out of the build that visitors get
const TestBench = import.meta.env.DEV ? lazy(() => import('./bench/TestBench.jsx')) : null

export default function App() {
  const route = useRoute()

  if (route === '/setup') return <Setup />
  if (route.startsWith('/game')) {
    // Every game has its own address; a bare #/game goes back to the one last played here
    const id = route.split('/')[2] ?? lastGame()
    if (!id) return <Setup />
    return <Game key={id} id={id} />
  }
  if (route === '/learn') return <Learn />
  if (route.startsWith('/scenarios')) return <Scenarios id={route.split('/')[2]} />
  if (TestBench && route === '/bench') {
    return (
      <Suspense fallback={null}>
        <TestBench />
      </Suspense>
    )
  }
  return <Home />
}
