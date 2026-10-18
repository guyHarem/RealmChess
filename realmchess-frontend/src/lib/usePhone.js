// True on a phone-sized screen. The game page is arranged differently there (see Game.jsx);
// the other pages only need the CSS in app.css.
import { useSyncExternalStore } from 'react'

export const PHONE = '(max-width: 760px)' // the same breakpoint as the phone rules in app.css

function subscribe(notify) {
  const media = window.matchMedia(PHONE)
  media.addEventListener('change', notify)
  return () => media.removeEventListener('change', notify)
}

export function usePhone() {
  return useSyncExternalStore(subscribe, () => window.matchMedia(PHONE).matches)
}
