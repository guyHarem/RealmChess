import { useState } from 'react'
import CubeBoard from '../components/CubeBoard.jsx'
import FeedbackButton from '../components/Feedback.jsx'
import Logo from '../components/Logo.jsx'
import { OFFLINE, openGame } from '../lib/api.js'
import { CLASSIC_CLOUDS, CLASSIC_DYNAMITE, CLASSIC_PORTALS, START_BOARD } from '../lib/chess.js'
import { navigate } from '../lib/router.js'
import { usePhone } from '../lib/usePhone.js'
import {
  CLOCK_PRESETS, LEVELS, PORTAL_CHOICES, clockRequest, cloudRequest, computerRequest, dynamiteRequest, levelName, loadSettings, playsComputer,
  portalRequest, saveSettings,
} from '../lib/settings.js'

function Choice({ selected, disabled, onClick, title, hint, children }) {
  return (
    <button
      type="button"
      className={`choice ${selected ? 'is-selected' : ''}`}
      aria-pressed={selected}
      disabled={disabled}
      onClick={onClick}
    >
      {children ?? title}
      {hint && <small>{hint}</small>}
    </button>
  )
}

function Switch({ label, checked, onChange }) {
  return (
    <button type="button" className="switch" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}>
      {label}
      <span className="switch-track">
        <span className="switch-knob" />
      </span>
    </button>
  )
}

export default function Setup() {
  const [settings, setSettings] = useState(loadSettings)
  const [sideChoice, setSideChoice] = useState(settings.side)
  const [error, setError] = useState(null)
  const [starting, setStarting] = useState(false)
  const set = (patch) => setSettings((current) => ({ ...current, ...patch }))
  const phone = usePhone()

  const limit = Number(settings.moveLimit)
  const limitValid = Number.isInteger(limit) && limit >= 10 && limit <= 200
  const clock = settings.clock
  const setClock = (patch) => set({ clock: { ...clock, ...patch } })
  const minutes = Number(clock.minutes)
  const increment = Number(clock.increment)
  const clockValid =
    clock.mode !== 'custom' ||
    (Number.isFinite(minutes) && minutes >= 1 && minutes <= 180 && Number.isInteger(increment) && increment >= 0 && increment <= 60)
  const clockSummary =
    clock.mode === 'none'
      ? 'No clock.'
      : clock.mode === 'custom'
        ? `${clock.minutes} min each${increment > 0 ? `, plus ${increment} s a move` : ''}.`
        : `${CLOCK_PRESETS.find((option) => option.mode === clock.mode).label} each.`
  // One short line: only the special cells that are on ("shuffled" when they are)
  const specials = ['portals', 'dynamite', 'clouds']
    .filter((name) => settings[name] !== 'off')
    .map((name) => (settings[name] === 'shuffle' ? `shuffled ${name}` : name))
  const rulesSummary = [
    settings.rocks ? 'Rocks' : 'No rocks',
    ...specials,
    settings.showLegalMoves ? 'moves shown' : 'moves hidden',
    settings.allowUndo ? 'undo' : 'no undo',
    `draw at ${settings.moveLimit}`,
  ].join(' · ')
  const previewSide = sideChoice === 'black' ? 'black' : 'white'
  const againstComputer = settings.opponent === 'computer'
  const online = settings.opponent === 'online'
  const teams = settings.teams
  const teamVsComputer = online && teams && settings.onlineRival === 'computer'
  const openToAll = online && settings.openGame
  const level = LEVELS.find((option) => option.id === settings.level)
  const previewBoard = settings.rocks
    ? START_BOARD
    : Object.fromEntries(Object.entries(START_BOARD).filter(([, value]) => value !== 'Rock'))

  // The special cells, all three set at once
  const allSpecials = ['portals', 'dynamite', 'clouds'].every((name) => settings[name] === 'classic')
  const specialSelect = (name, label) => (
    <div className="field">
      <label htmlFor={name}>{label}</label>
      <select id={name} value={settings[name]} onChange={(event) => set({ [name]: event.target.value })}>
        {PORTAL_CHOICES.map((choice) => (
          <option key={choice.id} value={choice.id}>
            {choice.label}
          </option>
        ))}
      </select>
    </div>
  )
  const rules = (
    <fieldset>
      <legend>Rules and help</legend>
      <div className="switches">
        <Switch label="Rocks in the dungeon" checked={settings.rocks} onChange={(rocks) => set({ rocks })} />
        <Switch
          label="Show legal moves"
          checked={settings.showLegalMoves}
          onChange={(showLegalMoves) => set({ showLegalMoves })}
        />
        <Switch label="Allow undo" checked={settings.allowUndo} onChange={(allowUndo) => set({ allowUndo })} />
        <div className="field">
          <label htmlFor="quiet">Draw after quiet moves</label>
          <input
            id="quiet"
            type="number"
            min="10"
            max="200"
            value={settings.moveLimit}
            aria-invalid={!limitValid}
            aria-describedby="quiet-help"
            onChange={(event) => set({ moveLimit: event.target.value })}
          />
        </div>
        <div className="special-cells">
          {specialSelect('portals', 'Portals')}
          {specialSelect('dynamite', 'Dynamite')}
          {specialSelect('clouds', 'Clouds')}
          <button
            type="button"
            className={`button special-preset ${allSpecials ? 'is-on' : ''}`}
            aria-pressed={allSpecials}
            onClick={() => set(allSpecials ? { portals: 'off', dynamite: 'off', clouds: 'off' } : { portals: 'classic', dynamite: 'classic', clouds: 'classic' })}
          >
            {allSpecials ? 'All off' : 'All Classic'}
          </button>
        </div>
      </div>
      <p id="quiet-help" className={`help ${limitValid ? '' : 'help-error'}`}>
        {limitValid
          ? 'Drawn when both make this many moves in a row with no capture or pawn move.'
          : 'Enter a whole number from 10 to 200.'}
      </p>
    </fieldset>
  )

  async function start() {
    setStarting(true)
    const side = sideChoice === 'random' ? (Math.random() < 0.5 ? 'white' : 'black') : sideChoice
    try {
      const data = await openGame({
        kind: online ? 'online' : againstComputer ? 'computer' : 'local',
        side,
        teams,
        public: openToAll || undefined,
        rocks: settings.rocks,
        move_limit: limit,
        clock: clockRequest(clock),
        computer: computerRequest(settings, side) ?? undefined,
        portals: portalRequest(settings),
        dynamite: dynamiteRequest(settings),
        clouds: cloudRequest(settings),
      })
      if (!data.success) throw new Error(data.error)
      saveSettings({ ...settings, side, moveLimit: limit })
      navigate(`/game/${data.game_id}`)
    } catch (problem) {
      setError(
        problem instanceof TypeError || problem instanceof SyntaxError
          ? OFFLINE
          : problem.message,
      )
      setStarting(false)
    }
  }

  return (
    <div className="page">
      <header className="bar">
        <Logo />
        <div className="bar-links">
          <FeedbackButton />
          <a className="bar-link" href="#/">
            Back to home
          </a>
        </div>
      </header>

      <main className="setup-main">
        <div className="setup-form">
          <h1>New game</h1>

          <fieldset>
            <legend>Opponent</legend>
            <div className="choices choices-3">
              <Choice
                selected={!againstComputer && !online}
                onClick={() => set({ opponent: 'local' })}
                title="Two players"
                hint="Same screen, take turns"
              />
              <Choice
                selected={againstComputer}
                onClick={() => set({ opponent: 'computer' })}
                title="Computer"
                hint="Pick a level below"
              />
              <Choice selected={online} onClick={() => set({ opponent: 'online' })} title="Online" hint="A friend, or anyone" />
            </div>
          </fieldset>

          {online && (
            <fieldset>
              <legend>Who can join</legend>
              <div className="choices">
                <Choice selected={!openToAll} onClick={() => set({ openGame: false })} title="A friend" hint="You send a link" />
                <Choice selected={openToAll} onClick={() => set({ openGame: true })} title="Anyone" hint="Listed in the lobby" />
              </div>
            </fieldset>
          )}

          <div className="setup-pair">
            <fieldset>
              <legend>Players</legend>
              <div className="choices">
                <Choice selected={!teams} onClick={() => set({ teams: false })} title="One a side" />
                <Choice selected={teams} onClick={() => set({ teams: true })} title="Teams of two" />
              </div>
            </fieldset>

            <fieldset>
              <legend>{againstComputer || online ? 'Your side' : 'Side nearest you'}</legend>
              <div className="choices">
                <Choice selected={sideChoice === 'white'} onClick={() => setSideChoice('white')}>
                  <i className="chip chip-white" />
                  White
                </Choice>
                <Choice selected={sideChoice === 'black'} onClick={() => setSideChoice('black')}>
                  <i className="chip chip-black" />
                  Black
                </Choice>
                <Choice selected={sideChoice === 'random'} onClick={() => setSideChoice('random')} title="Random" />
              </div>
            </fieldset>
          </div>

          {((online && teams) || playsComputer(settings)) && (
            <div className="setup-pair">
              {online && teams && (
                <fieldset>
                  <legend>Your team plays</legend>
                  <div className="choices">
                    <Choice selected={!teamVsComputer} onClick={() => set({ onlineRival: 'friends' })} title="Another team" />
                    <Choice selected={teamVsComputer} onClick={() => set({ onlineRival: 'computer' })} title="The computer" />
                  </div>
                </fieldset>
              )}

              {playsComputer(settings) && (
                <fieldset>
                  <legend>Computer level</legend>
                  <div className="choices">
                    {LEVELS.map((level) => (
                      <Choice
                        key={level.id}
                        selected={settings.level === level.id}
                        onClick={() => set({ level: level.id })}
                        title={level.label}
                      />
                    ))}
                  </div>
                </fieldset>
              )}
            </div>
          )}

          <fieldset>
            <legend>Clock</legend>
            <div className="choices">
              {CLOCK_PRESETS.map((option) => (
                <Choice
                  key={option.mode}
                  selected={clock.mode === option.mode}
                  onClick={() => setClock({ mode: option.mode })}
                  title={option.label}
                />
              ))}
            </div>
            {clock.mode === 'custom' && (
              <div className="switches">
                <div className="field">
                  <label htmlFor="clock-minutes">Minutes each</label>
                  <input
                    id="clock-minutes"
                    type="number"
                    min="1"
                    max="180"
                    value={clock.minutes}
                    aria-invalid={!clockValid}
                    aria-describedby="clock-help"
                    onChange={(event) => setClock({ minutes: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="clock-increment">Seconds added per move</label>
                  <input
                    id="clock-increment"
                    type="number"
                    min="0"
                    max="60"
                    value={clock.increment}
                    aria-invalid={!clockValid}
                    aria-describedby="clock-help"
                    onChange={(event) => setClock({ increment: event.target.value })}
                  />
                </div>
              </div>
            )}
            <p id="clock-help" className={`help ${clockValid ? '' : 'help-error'}`}>
              {clockValid
                ? 'A clock runs only on its player\'s turn, from White\'s first move. Run out and you lose.'
                : 'Minutes from 1 to 180, added seconds a whole number from 0 to 60.'}
            </p>
          </fieldset>

          {phone ? (
            // On a phone the rules fold into one line, so the page fits the screen
            <details className="setup-more" open={!limitValid || undefined}>
              <summary>
                <span>Rules and help</span>
                <small>{rulesSummary}</small>
              </summary>
              {rules}
            </details>
          ) : (
            rules
          )}

          {error && <p className="banner-error">{error}</p>}

          <div className="setup-actions">
            <button type="button" className="button button-primary button-large" disabled={!limitValid || !clockValid || starting} onClick={start}>
              {starting ? 'Starting' : online ? 'Create game' : 'Start game'}
            </button>
            <a className="bar-link" href="#/">
              Cancel
            </a>
          </div>
        </div>

        <aside className="setup-preview">
          <div className="setup-picture">
            <CubeBoard
              interactive={false}
              board={previewBoard}
              side={previewSide}
              portals={settings.portals === 'classic' ? CLASSIC_PORTALS : []}
              dynamite={settings.dynamite === 'classic' ? CLASSIC_DYNAMITE : []}
              clouds={settings.clouds === 'classic' ? CLASSIC_CLOUDS : []}
            />
          </div>
          <p className="setup-summary">
            <strong>
              {teams
                ? againstComputer
                  ? `You and a friend against the computer, ${levelName(settings.level)}`
                  : teamVsComputer
                    ? `Your team against the computer online, ${levelName(settings.level)}`
                    : online
                      ? openToAll ? 'Your team against anyone online' : 'Your team against another team online'
                      : 'Four players on this screen'
                : againstComputer
                  ? `You against the computer, ${levelName(settings.level)}`
                  : online
                    ? openToAll ? 'You against anyone online' : 'You against a friend online'
                    : 'Two players on this screen'}
            </strong>
            {teams
              ? `${
                  online
                    ? teamVsComputer
                      ? openToAll ? 'Anyone in the lobby can join as your teammate.' : 'You get a link for your teammate.'
                      : openToAll
                        ? 'Anyone in the lobby can take the free seats; you also get links to send.'
                        : 'You get two links: one for your teammate, one for the other team.'
                    : againstComputer
                      ? `${level.hint}.`
                      : 'Two a side.'
                } Teammates take turns with one army: ${
                  againstComputer || teamVsComputer
                    ? 'player 1 moves, the computer replies, then player 2'
                    : 'White 1, Black 1, White 2, Black 2'
                }, and round again.`
              : online
              ? `${openToAll ? 'Your game waits in the lobby for anyone to join.' : 'You get a link to send.'} ${
                  sideChoice === 'random' ? 'A coin flip decides your side.' : `You play ${previewSide === 'white' ? 'White and move first' : 'Black'}.`
                }`
              : againstComputer
              ? `${LEVELS.find((level) => level.id === settings.level).hint}. ${
                  sideChoice === 'random'
                    ? 'A coin flip decides your side.'
                    : `You play ${previewSide === 'white' ? 'White and move first' : 'Black; the computer moves first'}.`
                }`
              : sideChoice === 'random'
                ? 'A coin flip decides which side sits nearest.'
                : `${previewSide === 'white' ? 'White' : 'Black'} sits nearest. White moves first.`}
            <br />
            {clockSummary} {settings.rocks ? 'Rocks on.' : 'Rocks off.'}{' '}
            {{ off: '', classic: 'Portals: two linked pairs, Sky to Dungeon.', shuffle: 'Portals in random places, the same for both sides.' }[settings.portals]}{' '}
            {{ off: '', classic: 'Dynamite: four charges in the Sky and the Dungeon.', shuffle: 'Dynamite in random places, the same for both sides.' }[settings.dynamite]}{' '}
            {{ off: '', classic: 'Clouds: four shelters in Space and the Sky.', shuffle: 'Clouds in random places, the same for both sides.' }[settings.clouds]}{' '}
            {settings.allowUndo ? 'Undo allowed.' : 'No undo.'}
          </p>
        </aside>
      </main>
    </div>
  )
}
