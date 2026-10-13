import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import {
  cancelInvite, changePassword, createInvite, createResetCode, createToken, getServer, linkFor,
  listInvites, listPeople, listTokens, logOut, revokeToken, saveServer, updateMe,
} from '../api'
import type { Invite, Me, Person, TokenInfo } from '../types'
import { COUNTRIES, CURRENCIES, timeZones } from '../places'
import { shortDate } from '../format'
import { CloseIcon } from './Icons'

interface AccountSheetProps {
  me: Me
  onClose: () => void
  onChanged: (me: Me) => void // profile saved: the app re-reads the summary in the new currency
  onServerChanged: () => Promise<void>
}

// Everything about you: profile, keys for your devices, people (owner only),
// password, and logging out. Each part saves on its own.
export default function AccountSheet({ me, onClose, onChanged, onServerChanged }: AccountSheetProps) {
  // Close with the Escape key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="sheet-layer">
      <button className="scrim" aria-label="Close account" onClick={onClose} />
      <section className="card sheet" role="dialog" aria-modal="true" aria-labelledby="account-title">
        <div className="sheet-head">
          <div>
            <h2 id="account-title" className="serif sheet-title">Account</h2>
            <p className="budget-note">Signed in as {me.email}</p>
          </div>
          <button className="icon-btn" aria-label="Close account" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>

        <div className="sheet-body">
          <Profile me={me} onSaved={onChanged} />
          <Devices />
          {me.is_admin && <People />}
          <Password />
          <Connection onSaved={onServerChanged} />
          <button className="btn btn-secondary btn-wide" onClick={() => logOut()}>Log out</button>
        </div>
      </section>
    </div>
  )
}

// A titled part of the sheet.
function Part({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return (
    <section className="acct-part">
      <div>
        <h3 className="acct-title">{title}</h3>
        {note && <p className="budget-note">{note}</p>}
      </div>
      {children}
    </section>
  )
}

function Message({ text }: { text: { text: string; tone: 'muted' | 'warn' } | null }) {
  if (!text) return null
  return <p className={text.tone === 'warn' ? 'budget-note add-msg is-warn' : 'budget-note add-msg'} role="status">{text.text}</p>
}

type Msg = { text: string; tone: 'muted' | 'warn' } | null
const failed = (err: unknown): Msg => ({ text: (err as Error).message, tone: 'warn' })

// ------------------------------------------------------------------ profile

function Profile({ me, onSaved }: { me: Me; onSaved: (me: Me) => void }) {
  const [name, setName] = useState(me.name)
  const [country, setCountry] = useState(me.country)
  const [currency, setCurrency] = useState(me.currency)
  const [zone, setZone] = useState(me.timezone)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<Msg>(null)
  const zones = timeZones()
  const countries = COUNTRIES.some((c) => c.code === country) ? COUNTRIES
    : [...COUNTRIES, { code: country, name: country, currency, zone }]

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      onSaved(await updateMe({ name, country, currency, timezone: zone }))
      setMsg({ text: 'Saved.', tone: 'muted' })
    } catch (err) {
      setMsg(failed(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Part title="You" note="Prices show in your currency; “this month” follows your time zone. OnTrack doesn’t convert currencies.">
      <form className="acct-form" onSubmit={save}>
        <input className="field" aria-label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="auth-grid">
          <select className="field" aria-label="Country" value={country} onChange={(e) => setCountry(e.target.value)}>
            {countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
          </select>
          <select className="field" aria-label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select className="field is-wide" aria-label="Time zone" value={zone} onChange={(e) => setZone(e.target.value)}>
            {(zones.includes(zone) ? zones : [zone, ...zones]).map((z) => <option key={z} value={z}>{z.replaceAll('_', ' ')}</option>)}
          </select>
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </form>
      <Message text={msg} />
    </Part>
  )
}

// ------------------------------------------------------------------ devices

function Devices() {
  const [tokens, setTokens] = useState<TokenInfo[] | null>(null)
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null)
  const [msg, setMsg] = useState<Msg>(null)

  const load = () => listTokens().then(setTokens).catch((err) => setMsg(failed(err)))
  useEffect(() => {
    load()
  }, [])

  async function create(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      setFresh(await createToken(name.trim() || 'Device'))
      setName('')
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  async function revoke(t: TokenInfo) {
    try {
      await revokeToken(t.id)
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  return (
    <Part title="Devices" note="Each Shortcut and the browser extension gets its own key. Lost a phone? Remove its key here.">
      {fresh && (
        <Reveal label={`Key for “${fresh.name}”`} value={fresh.token}
          hint="Shown only once. Paste it as the X-API-Key in your Shortcut, or as the API key in the extension." />
      )}
      <ul className="acct-list">
        {tokens?.map((t) => (
          <li key={t.id} className="acct-row">
            <div className="acct-row-text">
              <span className="acct-row-name">{t.name}{t.current && <span className="tag">This browser</span>}</span>
              <span className="budget-note">{t.kind === 'session' ? 'Login' : 'Device key'} · {t.last_used_at ? `last used ${shortDate(t.last_used_at)}` : `added ${shortDate(t.created_at)}`}</span>
            </div>
            {!t.current && <button className="btn btn-quiet" onClick={() => revoke(t)}>Remove</button>}
          </li>
        ))}
      </ul>
      <form className="add-form" onSubmit={create}>
        <input className="field add-input" aria-label="Device name" placeholder="e.g. iPhone Shortcuts" maxLength={60}
          value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn btn-secondary add-btn" type="submit">New key</button>
      </form>
      <Message text={msg} />
    </Part>
  )
}

// ------------------------------------------------------------ people (owner)

function People() {
  const [people, setPeople] = useState<Person[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [note, setNote] = useState('')
  const [fresh, setFresh] = useState<{ label: string; link: string } | null>(null)
  const [msg, setMsg] = useState<Msg>(null)

  const load = () =>
    Promise.all([listPeople(), listInvites()])
      .then(([p, i]) => {
        setPeople(p)
        setInvites(i.filter((x) => !x.used_at && x.expires_at > new Date().toISOString()))
      })
      .catch((err) => setMsg(failed(err)))
  useEffect(() => {
    load()
  }, [])

  async function invite(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      const { code } = await createInvite(note.trim())
      setFresh({ label: `Invite link${note.trim() ? ` for ${note.trim()}` : ''}`, link: linkFor('invite', code) })
      setNote('')
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  async function reset(p: Person) {
    setMsg(null)
    try {
      const { code } = await createResetCode(p.id)
      setFresh({ label: `Password reset for ${p.name}`, link: linkFor('reset', code) })
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  async function cancel(i: Invite) {
    try {
      await cancelInvite(i.id)
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  return (
    <Part title="People" note="OnTrack is invite-only. An invite works once, for 7 days; a reset link for 2.">
      {fresh && <Reveal label={fresh.label} value={fresh.link} hint="Send this link yourself (message or email). It works once." />}
      <ul className="acct-list">
        {people.map((p) => (
          <li key={p.id} className="acct-row">
            <div className="acct-row-text">
              <span className="acct-row-name">{p.name}{p.is_admin && <span className="tag">Owner</span>}</span>
              <span className="budget-note">{p.email} · {p.items} {p.items === 1 ? 'item' : 'items'}</span>
            </div>
            <button className="btn btn-quiet" onClick={() => reset(p)}>Reset link</button>
          </li>
        ))}
        {invites.map((i) => (
          <li key={`i${i.id}`} className="acct-row">
            <div className="acct-row-text">
              <span className="acct-row-name">{i.for_email ? `Reset for ${i.for_email}` : `Invite${i.note ? ` · ${i.note}` : ''}`}</span>
              <span className="budget-note">Not used yet · until {shortDate(i.expires_at)}</span>
            </div>
            <button className="btn btn-quiet" onClick={() => cancel(i)}>Cancel</button>
          </li>
        ))}
      </ul>
      <form className="add-form" onSubmit={invite}>
        <input className="field add-input" aria-label="Who is it for?" placeholder="Who is it for? (optional)" maxLength={80}
          value={note} onChange={(e) => setNote(e.target.value)} />
        <button className="btn btn-secondary add-btn" type="submit">Invite</button>
      </form>
      <Message text={msg} />
    </Part>
  )
}

// ------------------------------------------------------------------ password

function Password() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [msg, setMsg] = useState<Msg>(null)

  async function save(e: FormEvent) {
    e.preventDefault()
    setMsg(null)
    try {
      await changePassword(current, next)
      setCurrent('')
      setNext('')
      setMsg({ text: 'Password changed. Your other logins were signed out; device keys still work.', tone: 'muted' })
    } catch (err) {
      setMsg(failed(err))
    }
  }

  return (
    <Part title="Password">
      <form className="acct-form" onSubmit={save}>
        <input className="field" type="password" aria-label="Current password" placeholder="Current password"
          autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        <input className="field" type="password" aria-label="New password" placeholder="New password (10+ characters)"
          autoComplete="new-password" minLength={10} required value={next} onChange={(e) => setNext(e.target.value)} />
        <button className="btn btn-secondary" type="submit">Change password</button>
      </form>
      <Message text={msg} />
    </Part>
  )
}

// ---------------------------------------------------------------- connection

function Connection({ onSaved }: { onSaved: () => Promise<void> }) {
  const [server, setServer] = useState(getServer())
  async function save(e: FormEvent) {
    e.preventDefault()
    saveServer(server)
    await onSaved()
  }
  return (
    <details className="auth-server">
      <summary>Server address</summary>
      <form className="add-form" onSubmit={save}>
        <input className="field add-input" type="url" aria-label="Server address" value={server}
          onChange={(e) => setServer(e.target.value)} />
        <button className="btn btn-secondary add-btn" type="submit">Save</button>
      </form>
    </details>
  )
}

// ------------------------------------------------------------------ helpers

// A new key or link, shown once, with a Copy button.
function Reveal({ label, value, hint }: { label: string; value: string; hint: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      setCopied(false) // no clipboard access: the text can still be selected by hand
    }
  }
  return (
    <div className="reveal fade-in">
      <span className="eyebrow">{label}</span>
      <code className="reveal-value">{value}</code>
      <div className="reveal-foot">
        <p className="budget-note">{hint}</p>
        <button className="btn btn-primary" type="button" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
      </div>
    </div>
  )
}
