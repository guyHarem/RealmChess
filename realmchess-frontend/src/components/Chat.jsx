// Online team games: messages between teammates, and the moves they suggest to each other.
// Only your own team's messages reach this page.
import { useEffect, useRef, useState } from 'react'

export default function TeamChat({ messages, mySeat, canSuggest, describe, onSay }) {
  const [text, setText] = useState('')
  const box = useRef(null)
  const count = messages.length

  // Keep the newest message in view
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [count])

  function send(event) {
    event.preventDefault()
    if (!text.trim()) return
    onSay(text)
    setText('')
  }

  return (
    <section className="team-chat" aria-label="Team messages">
      <h2>Your team</h2>
      <div className="team-chat-box" ref={box} aria-live="polite">
        {count === 0 && (
          <p className="team-chat-empty">
            Only your teammate sees these. {canSuggest ? '' : 'On their turn, pick a piece and a square to suggest a move.'}
          </p>
        )}
        {messages.map((message) => (
          <p key={message.id} className={message.seat === mySeat ? 'is-mine' : ''}>
            <strong>{message.seat === mySeat ? 'You' : 'Teammate'}</strong>
            {message.move && (
              <span className="team-chat-move">
                {' '}
                {message.seat === mySeat ? 'suggested' : 'suggests'} {describe(message)}
              </span>
            )}
            {message.text && <span>{message.move ? ': ' : ' '}{message.text}</span>}
          </p>
        ))}
      </div>
      {canSuggest && <p className="team-chat-tip">Your teammate's turn: pick a piece and a square to suggest a move.</p>}
      <form className="team-chat-form" onSubmit={send}>
        <input
          type="text"
          maxLength={200}
          value={text}
          placeholder="Message your teammate"
          aria-label="Message your teammate"
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" className="button" disabled={!text.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
