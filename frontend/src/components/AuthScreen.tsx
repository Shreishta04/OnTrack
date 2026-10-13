import { useState, type FormEvent, type ReactNode } from 'react'
import { getServer, logIn, resetPassword, saveServer, signUp } from '../api'
import type { Me } from '../types'
import { COUNTRIES, CURRENCIES, deviceZone, guessCountry, timeZones } from '../places'

export type AuthMode = 'login' | 'signup' | 'reset'

interface AuthScreenProps {
  mode: AuthMode
  code: string // from an invite or reset link; '' when typed by hand
  onSignedIn: (me: Me) => void
}

const TITLES: Record<AuthMode, { title: string; note: string }> = {
  login: { title: 'Welcome back', note: 'Log in to see your wish list.' },
  signup: { title: 'Join OnTrack', note: 'Your own wish list and budget, private to you.' },
  reset: { title: 'New password', note: 'Choose a new password for your account.' },
}

// The first screen anyone sees: log in, sign up with an invite, or use a
// password-reset link. OnTrack is invite-only, so signing up needs a code.
export default function AuthScreen({ mode: startMode, code: startCode, onSignedIn }: AuthScreenProps) {
  const [mode, setMode] = useState<AuthMode>(startMode)
  const [code, setCode] = useState(startCode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const guess = guessCountry()
  const [country, setCountry] = useState(guess.code)
  const [currency, setCurrency] = useState(guess.currency)
  const [zone, setZone] = useState(deviceZone())
  const [server, setServer] = useState(getServer())
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  // Picking a country suggests its currency (you can still change it).
  function pickCountry(codeValue: string) {
    setCountry(codeValue)
    const c = COUNTRIES.find((x) => x.code === codeValue)
    if (c) setCurrency(c.currency)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page
    setBusy(true)
    setProblem(null)
    saveServer(server)
    try {
      const me =
        mode === 'login'
          ? await logIn(email, password)
          : mode === 'signup'
            ? await signUp({ invite: code, email, password, name, currency, country, timezone: zone })
            : await resetPassword(code, password)
      onSignedIn(me)
    } catch (err) {
      setProblem((err as Error).message)
      setBusy(false)
    }
  }

  const { title, note } = TITLES[mode]
  const zones = timeZones()

  return (
    <div className="auth-page">
      <div className="auth-brand">
        <div className="brand">OnTrack</div>
        <div className="eyebrow">Your wish list, on budget</div>
      </div>

      <section className="card auth-card fade-in" key={mode}>
        <div>
          <h1 className="serif auth-title">{title}</h1>
          <p className="budget-note">{note}</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'signup' && !startCode && (
            <Field label="Invite code" id="invite">
              <input id="invite" className="field" required autoComplete="off" value={code}
                onChange={(e) => setCode(e.target.value)} placeholder="From your invite link" />
            </Field>
          )}
          {mode === 'signup' && (
            <Field label="Your name" id="name">
              <input id="name" className="field" autoComplete="given-name" value={name}
                onChange={(e) => setName(e.target.value)} placeholder="What should OnTrack call you?" />
            </Field>
          )}
          {mode !== 'reset' && (
            <Field label="Email" id="email">
              <input id="email" className="field" type="email" required autoComplete="email" value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </Field>
          )}
          <Field label={mode === 'login' ? 'Password' : 'Choose a password'} id="password">
            <input id="password" className="field" type="password" required
              minLength={mode === 'login' ? undefined : 10}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={mode === 'login' ? '' : 'At least 10 characters'} />
          </Field>

          {mode === 'signup' && (
            <div className="auth-grid">
              <Field label="Country" id="country">
                <select id="country" className="field" value={country} onChange={(e) => pickCountry(e.target.value)}>
                  {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Currency" id="currency">
                <select id="currency" className="field" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Time zone" id="zone" wide>
                <select id="zone" className="field" value={zone} onChange={(e) => setZone(e.target.value)}>
                  {(zones.includes(zone) ? zones : [zone, ...zones]).map((z) => (
                    <option key={z} value={z}>{z.replaceAll('_', ' ')}</option>
                  ))}
                </select>
              </Field>
            </div>
          )}

          {problem && <p className="notice notice-error" role="alert">{problem}</p>}

          <button className="btn btn-primary btn-wide" type="submit" disabled={busy}>
            {busy ? 'One moment…' : mode === 'login' ? 'Log in' : mode === 'signup' ? 'Create account' : 'Save password'}
          </button>
        </form>

        <div className="auth-switch">
          {mode === 'login' ? (
            <button className="link-btn" type="button" onClick={() => setMode('signup')}>
              Have an invite? Create your account
            </button>
          ) : (
            <button className="link-btn" type="button" onClick={() => setMode('login')}>
              Already have an account? Log in
            </button>
          )}
          {mode === 'login' && (
            <p className="budget-note">Forgot your password? Ask the person who invited you for a reset link.</p>
          )}
        </div>

        <details className="auth-server">
          <summary>Server</summary>
          <input className="field" type="url" aria-label="Server address" value={server}
            onChange={(e) => setServer(e.target.value)} />
        </details>
      </section>
    </div>
  )
}

function Field({ label, id, wide, children }: { label: string; id: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={wide ? 'field-group is-wide' : 'field-group'}>
      <label className="eyebrow" htmlFor={id}>{label}</label>
      {children}
    </div>
  )
}
