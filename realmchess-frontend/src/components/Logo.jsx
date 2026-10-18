// The castle rook in five floors, one per layer: Space, Sky, Ground, Dungeon, Abyss

export function LogoMark({ size = 34 }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true">
      <path d="M22 10h13v10h8V10h14v10h8V10h13v14H22Z" fill="#4A78D6" />
      <path d="M22 27h56v5l-9 8v1H31v-1l-9-8Z" fill="#7EC3F2" />
      <path d="M31 44h38v14H31Z" fill="#86CF7A" />
      <path d="M31 61h38v11l3.375 3h-44.75L31 72Z" fill="#B49AE8" />
      <path d="M24.25 78h51.5L78 80v12H22V80Z" fill="#6B4FB8" />
    </svg>
  )
}

export function Wordmark() {
  return (
    <span className="wordmark">
      Realm<span>Chess</span>
    </span>
  )
}

export default function Logo() {
  return (
    <a className="logo" href="#/">
      <LogoMark />
      <Wordmark />
    </a>
  )
}
