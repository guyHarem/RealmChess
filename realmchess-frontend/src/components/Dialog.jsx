// A small centred panel over the board (promotion choice, confirmations, game over)

export default function Dialog({ title, children, actions }) {
  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {children}
        <div className="dialog-actions">{actions}</div>
      </div>
    </div>
  )
}
