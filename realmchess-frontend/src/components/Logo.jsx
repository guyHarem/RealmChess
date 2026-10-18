// The "three worlds" cube: ground on top, sky on the left, abyss on the right

export function LogoMark({ size = 34 }) {
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} aria-hidden="true">
      <polygon points="50,8 86,29 50,50 14,29" fill="#C4EBB9" />
      <polygon points="50,8 68,18.5 50,29 32,18.5" fill="#86CF7A" />
      <polygon points="50,29 68,39.5 50,50 32,39.5" fill="#86CF7A" />
      <polygon points="14,29 50,50 50,92 14,71" fill="#7EC3F2" />
      <polygon points="50,50 86,29 86,71 50,92" fill="#6B4FB8" />
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
