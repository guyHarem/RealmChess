// Finished lessons and solved puzzles, remembered in this browser across visits.
// Storage can be unavailable (private windows); progress is a convenience, so the pages
// carry on without it.

export const LESSONS = 'realmchess.lessons'
export const PUZZLES = 'realmchess.scenarios'

export function loadIds(key) {
  try {
    let saved = localStorage.getItem(key)
    if (saved === null) {
      // Progress used to last only as long as the tab: keep what this tab had
      saved = sessionStorage.getItem(key)
      if (saved !== null) localStorage.setItem(key, saved)
    }
    const ids = JSON.parse(saved ?? '[]')
    return Array.isArray(ids) ? ids : []
  } catch {
    return []
  }
}

// Remember one more id; returns the whole list
export function addId(key, id) {
  const ids = loadIds(key)
  if (ids.includes(id)) return ids
  const next = [...ids, id]
  try {
    localStorage.setItem(key, JSON.stringify(next))
  } catch {
    // see above
  }
  return next
}

export function clearProgress() {
  for (const key of [LESSONS, PUZZLES]) {
    try {
      localStorage.removeItem(key)
      sessionStorage.removeItem(key)
    } catch {
      // see above
    }
  }
}
