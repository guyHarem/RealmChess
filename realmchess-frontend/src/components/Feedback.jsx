// The Feedback button in the top bar: a short form whose message goes to the admin page
import { useEffect, useRef, useState } from 'react'
import { sendFeedback } from '../lib/api.js'

const KINDS = [
  { id: 'bug', label: 'Something is wrong' },
  { id: 'idea', label: 'An idea' },
  { id: 'other', label: 'Something else' },
]

export default function FeedbackButton({ className = 'bar-link link-plain', game = null }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}>
        Feedback
      </button>
      {open && <FeedbackForm game={game} onClose={() => setOpen(false)} />}
    </>
  )
}

export function FeedbackForm({ game, onClose }) {
  const [kind, setKind] = useState('idea')
  const [text, setText] = useState('')
  const [contact, setContact] = useState('')
  const [state, setState] = useState('writing') // 'writing' | 'sending' | 'sent'
  const [error, setError] = useState(null)
  const box = useRef(null)

  useEffect(() => {
    box.current?.focus()
    const onKey = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function submit(event) {
    event.preventDefault()
    setState('sending')
    try {
      const data = await sendFeedback({ kind, text, contact, page: window.location.hash.replace(/^#/, '') || '/', game })
      if (!data.success) throw new Error(data.error)
      setState('sent')
    } catch (problem) {
      setError(problem instanceof TypeError || problem instanceof SyntaxError ? 'It could not be sent. Try again in a moment.' : problem.message)
      setState('writing')
    }
  }

  return (
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <form className="dialog feedback" role="dialog" aria-modal="true" aria-label="Feedback" onSubmit={submit}>
        <h2>{state === 'sent' ? 'Thank you' : 'Feedback'}</h2>
        {state === 'sent' ? (
          <p>Your message has been sent. It helps make RealmChess better.</p>
        ) : (
          <>
            <p>Found a problem, or have an idea? Tell us.</p>
            <div className="feedback-kinds" role="radiogroup" aria-label="What is it about">
              {KINDS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={kind === option.id}
                  className={`choice ${kind === option.id ? 'is-selected' : ''}`}
                  onClick={() => setKind(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <label className="feedback-field">
              <span>Your message</span>
              <textarea
                ref={box}
                rows={5}
                maxLength={2000}
                value={text}
                placeholder={kind === 'bug' ? 'What happened, and what did you expect?' : 'Tell us what you think'}
                onChange={(event) => setText(event.target.value)}
              />
            </label>
            <label className="feedback-field">
              <span>How to reach you (optional)</span>
              <input type="text" maxLength={200} value={contact} placeholder="Email or name" onChange={(event) => setContact(event.target.value)} />
            </label>
            {error && <p className="banner-error">{error}</p>}
          </>
        )}
        <div className="dialog-actions">
          {state !== 'sent' && (
            <button type="submit" className="button button-primary" disabled={!text.trim() || state === 'sending'}>
              {state === 'sending' ? 'Sending' : 'Send'}
            </button>
          )}
          <button type="button" className="button" onClick={onClose}>
            {state === 'sent' ? 'Close' : 'Cancel'}
          </button>
        </div>
      </form>
    </div>
  )
}
