// Messages in an online game: to everyone playing, and in a team game to your teammate (with
// the moves you suggest to each other). In an open game the players are strangers, so they
// pick from a few phrases instead of typing.
import { useEffect, useRef, useState } from 'react'

// toEveryone: false for a team playing the computer, which only talks to itself
export default function Chat({ messages, mySeat, teams, toEveryone = true, phrases, canSuggest, describe, onSay }) {
  const [text, setText] = useState('')
  const [to, setTo] = useState(teams ? 'team' : 'all')
  const box = useRef(null)
  const count = messages.length
  const myColor = mySeat?.slice(0, 5)

  // Keep the newest message in view
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [count])

  function send(event) {
    event.preventDefault()
    if (!text.trim()) return
    onSay(text, to)
    setText('')
  }

  const who = (message) => {
    if (message.seat === mySeat) return 'You'
    if (message.seat.slice(0, 5) === myColor) return 'Teammate'
    return teams ? 'Other team' : 'Opponent'
  }
  const toTeam = teams && to === 'team'

  return (
    <section className="chat" aria-label="Messages">
      <div className="chat-head">
        <h2>Messages</h2>
        {teams && toEveryone && (
          <div className="chat-to" role="group" aria-label="Send to">
            <button type="button" className={`button ${to === 'team' ? 'is-on' : ''}`} aria-pressed={to === 'team'} onClick={() => setTo('team')}>
              Team
            </button>
            <button type="button" className={`button ${to === 'all' ? 'is-on' : ''}`} aria-pressed={to === 'all'} onClick={() => setTo('all')}>
              Everyone
            </button>
          </div>
        )}
      </div>
      <div className="chat-box" ref={box} aria-live="polite">
        {count === 0 && (
          <p className="chat-empty">
            {teams
              ? `Team messages only reach your teammate. ${canSuggest ? '' : 'On their turn, pick a piece and a square to suggest a move.'}`
              : phrases ? 'Say hello to your opponent.' : 'Messages reach your opponent.'}
          </p>
        )}
        {messages.map((message) => (
          <p key={message.id} className={message.seat === mySeat ? 'is-mine' : message.to === 'all' && teams ? 'is-all' : ''}>
            <strong>{who(message)}</strong>
            {teams && message.to === 'all' && <small> to everyone</small>}
            {message.move && (
              <span className="chat-move">
                {' '}
                {message.seat === mySeat ? 'suggested' : 'suggests'} {describe(message)}
              </span>
            )}
            {message.text && <span>{message.move ? ': ' : ' '}{message.text}</span>}
          </p>
        ))}
      </div>
      {canSuggest && <p className="chat-tip">Your teammate's turn: pick a piece and a square to suggest a move.</p>}
      {phrases ? (
        <div className="chat-phrases" role="group" aria-label={toTeam ? 'Say to your teammate' : 'Say to everyone'}>
          {phrases.map((phrase) => (
            <button key={phrase} type="button" className="chat-phrase" onClick={() => onSay(phrase, to)}>
              {phrase}
            </button>
          ))}
        </div>
      ) : (
        <form className="chat-form" onSubmit={send}>
          <input
            type="text"
            maxLength={200}
            value={text}
            placeholder={toTeam ? 'Message your teammate' : teams ? 'Message everyone' : 'Message your opponent'}
            aria-label={toTeam ? 'Message your teammate' : teams ? 'Message everyone' : 'Message your opponent'}
            onChange={(event) => setText(event.target.value)}
          />
          <button type="submit" className="button" disabled={!text.trim()}>
            Send
          </button>
        </form>
      )}
    </section>
  )
}
