import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import {
  cancelInvite, changePassword, createInvite, createResetCode, createToken, getNotify, getServer, getTrash, linkFor,
  listInvites, listPeople, listTokens, logOut, removeAccess, restoreAccess, revokeToken, saveServer, sendTestAlert,
  setNotify, updateMe,
} from '../api'
import type { AlertKind, Invite, Me, NotifySettings, Person, Summary, TokenInfo } from '../types'
import { alertState, turnOnAlerts, type AlertState } from '../alerts'
import type { ThemePref } from '../hooks/useTheme'
import { COUNTRIES, CURRENCIES, timeZones } from '../places'
import { dayMonth, ordinal, shortDate } from '../format'
import { useEdgeBack } from '../hooks/useEdgeBack'
import { device, phoneSetUp } from '../device'
import { useMoney } from '../money'
import BudgetEditor from './BudgetEditor'
import Price from './Price'
import {
  BackIcon, BellIcon, BoxIcon, CalendarIcon, ChevronRightIcon, ClockIcon, GlobeIcon, KeyIcon, LockIcon, LogOutIcon,
  MoonIcon, PeopleIcon, PhoneIcon, SunIcon, TagDownIcon, TrashIcon, WalletIcon,
} from './Icons'

interface SettingsPageProps {
  me: Me
  summary: Summary | null
  theme: { pref: ThemePref; setPref: (pref: ThemePref) => void }
  notes: ReactNode // offline / new version / what just happened (the same lines as on the list)
  onBack: () => void
  onMe: (me: Me) => void // profile or region saved
  onBudgetSaved: () => Promise<void>
  onServerChanged: () => Promise<void>
  onOpenSetup: () => void // Set up this phone
  onOpenTrash: () => void // Recently deleted
}

type Part = 'profile' | 'budget' | 'region' | 'password' | 'devices' | 'people'

// Settings, as a page of its own (/settings). Each row opens its editor right
// underneath it; one at a time, so the page never gets long.
export default function SettingsPage({
  me, summary, theme, notes, onBack, onMe, onBudgetSaved, onServerChanged, onOpenSetup, onOpenTrash,
}: SettingsPageProps) {
  const [open, setOpen] = useState<Part | null>(null)
  const [keyCount, setKeyCount] = useState<number | null>(null)
  const [trashCount, setTrashCount] = useState<number | null>(null)
  const money = useMoney()
  const toggle = (part: Part) => setOpen(open === part ? null : part)
  const country = COUNTRIES.find((c) => c.code === me.country)?.name ?? me.country

  // How many items are in Recently deleted, for its row (an older server has no /trash).
  useEffect(() => {
    getTrash()
      .then((items) => setTrashCount(Array.isArray(items) ? items.length : null))
      .catch(() => setTrashCount(null))
  }, [])

  // How many device keys there are, for the row's number (logins don't count).
  useEffect(() => {
    listTokens()
      .then((tokens) => setKeyCount(tokens.filter((t) => t.kind !== 'session').length))
      .catch(() => setKeyCount(null))
  }, [])

  const edgeBack = useEdgeBack(onBack) // the iPhone home-screen app's back swipe
  const period = summary?.period
  const defaultBudget = period ? period.default_budget : summary?.budget

  return (
    <div className="page settings-page" {...edgeBack}>
      <div className="settings-top">
        <button className="icon-btn" aria-label="Back to your list" onClick={onBack}>
          <BackIcon />
        </button>
      </div>
      <h1 className="settings-title">Settings</h1>
      {notes}

      <div className="set-group">
        <Row
          big
          icon={<span className="avatar">{me.name.trim().charAt(0).toUpperCase() || '?'}</span>}
          label={me.name}
          sub={me.email}
          open={open === 'profile'}
          onToggle={() => toggle('profile')}
        >
          <NameForm me={me} onSaved={onMe} />
        </Row>
        {/* its own page: the steps differ for iPhone, Android and computers */}
        <Row
          icon={<PhoneIcon />}
          label="Set up this phone"
          sub={device() === 'computer' ? 'Sharing from your phone, and the browser extension' : 'Add products by sharing them'}
          value={phoneSetUp() ? 'Done' : undefined}
          open={false}
          onToggle={onOpenSetup}
        />
      </div>

      <h2 className="set-heading">Appearance</h2>
      <div className="segmented" role="radiogroup" aria-label="Appearance">
        <Choice on={theme.pref === 'light'} onPick={() => theme.setPref('light')} icon={<SunIcon />} label="Light" />
        <Choice on={theme.pref === 'dark'} onPick={() => theme.setPref('dark')} icon={<MoonIcon />} label="Dark" />
        <Choice on={theme.pref === 'system'} onPick={() => theme.setPref('system')} icon={<PhoneIcon />} label="Auto" />
      </div>
      <p className="set-note">Auto follows your phone’s own light or dark setting.</p>

      <h2 className="set-heading">Notifications</h2>
      <Notifications />

      <h2 className="set-heading">Budget</h2>
      <div className="set-group">
        <Row
          icon={<WalletIcon />}
          label="Monthly budget"
          value={defaultBudget == null ? 'Not set' : <Price amount={defaultBudget} />}
          open={open === 'budget'}
          onToggle={() => toggle('budget')}
        />
        {/* both rows open the same editor, underneath the second (like Region) */}
        {period && (
          <Row
            icon={<CalendarIcon />}
            label="Resets on"
            value={period.reset_day == null ? 'Not set' : `the ${ordinal(period.reset_day)}`}
            open={open === 'budget'}
            onToggle={() => toggle('budget')}
          />
        )}
        {open === 'budget' && (
          <div className="set-panel fade-in">
            <BudgetEditor
              period={period}
              current={summary?.budget ?? null}
              onCancel={() => setOpen(null)}
              onSaved={async () => {
                await onBudgetSaved()
                setOpen(null)
              }}
            />
          </div>
        )}
      </div>
      {period?.custom && period.budget != null && (
        <p className="set-note">
          This period ({dayMonth(period.starts_on)} – {dayMonth(period.ends_on)}) has its own budget,{' '}
          <Price amount={period.budget} />, set just for it.
        </p>
      )}

      <h2 className="set-heading">Region</h2>
      <div className="set-group">
        <Row icon={<span className="set-icon-text">{money.symbol}</span>} label="Currency" value={me.currency}
          open={open === 'region'} onToggle={() => toggle('region')} />
        <Row icon={<GlobeIcon />} label="Country" value={country}
          open={open === 'region'} onToggle={() => toggle('region')} />
        <Row icon={<ClockIcon />} label="Time zone" value={me.timezone.replaceAll('_', ' ')}
          open={open === 'region'} onToggle={() => toggle('region')}>
          <RegionForm me={me} onSaved={onMe} />
        </Row>
      </div>

      <h2 className="set-heading">Account</h2>
      <div className="set-group">
        <Row icon={<TrashIcon />} label="Recently deleted" value={trashCount || undefined} open={false} onToggle={onOpenTrash} />
        <Row icon={<LockIcon />} label="Change password" open={open === 'password'} onToggle={() => toggle('password')}>
          <Password />
        </Row>
        <Row icon={<KeyIcon />} label="Shortcuts and extension" value={keyCount ?? undefined}
          open={open === 'devices'} onToggle={() => toggle('devices')}>
          <Devices onCount={setKeyCount} />
        </Row>
        {me.is_admin && (
          <Row icon={<PeopleIcon />} label="People and invites" open={open === 'people'} onToggle={() => toggle('people')}>
            <People />
          </Row>
        )}
      </div>

      <button className="set-logout" onClick={() => logOut()}>
        <LogOutIcon />
        Log out
      </button>

      <Connection onSaved={onServerChanged} />
    </div>
  )
}

// ------------------------------------------------------------------ layout

// One row: an icon, a label, maybe a value, and a ">" that turns down while
// its editor (the children) is open underneath. The three Region rows share
// one editor, so only the last of them has children.
function Row({ icon, label, sub, value, open, onToggle, big, children }: {
  icon: ReactNode
  label: string
  sub?: string
  value?: ReactNode
  open: boolean
  onToggle: () => void
  big?: boolean
  children?: ReactNode
}) {
  return (
    <>
      <button className={big ? 'set-row is-big' : 'set-row'} aria-expanded={open} onClick={onToggle}>
        <span className="set-icon">{icon}</span>
        <span className="set-label">
          {label}
          {sub && <span className="set-sub">{sub}</span>}
        </span>
        {value != null && <span className="set-value">{value}</span>}
        <span className={open ? 'set-chevron is-open' : 'set-chevron'}>
          <ChevronRightIcon />
        </span>
      </button>
      {open && children && <div className="set-panel fade-in">{children}</div>}
    </>
  )
}

function Choice({ on, onPick, icon, label }: { on: boolean; onPick: () => void; icon: ReactNode; label: string }) {
  return (
    <button className={on ? 'segment is-on' : 'segment'} role="radio" aria-checked={on} onClick={onPick}>
      {icon}
      {label}
    </button>
  )
}

function Message({ text }: { text: Msg }) {
  if (!text) return null
  return <p className={text.tone === 'warn' ? 'budget-note add-msg is-warn' : 'budget-note add-msg'} role="status">{text.text}</p>
}

type Msg = { text: string; tone: 'muted' | 'warn' } | null
const failed = (err: unknown): Msg => ({ text: (err as Error).message, tone: 'warn' })

// ------------------------------------------------------------ notifications

const ALERTS: { kind: AlertKind; icon: ReactNode; label: string; sub: string }[] = [
  { kind: 'price_drop', icon: <TagDownIcon />, label: 'Price dropped', sub: 'Something on your list got cheaper' },
  { kind: 'back_in_stock', icon: <BoxIcon />, label: 'Back in stock', sub: 'It was sold out, now it isn’t' },
  { kind: 'budget_reset', icon: <CalendarIcon />, label: 'Budget resets tomorrow', sub: 'On the last day of each period' },
  { kind: 'waiting', icon: <ClockIcon />, label: 'Still on your list', sub: 'Mondays: things waiting 2+ weeks' },
]

const STATE_LINE: Record<AlertState, string> = {
  on: 'On for this phone',
  off: 'Off for this phone',
  blocked: 'Blocked in your phone’s settings',
  'home-screen': 'Open OnTrack from your Home Screen to turn on',
  unsupported: 'This browser can’t show alerts',
}

// Turn alerts on for this phone, choose which ones, and send a test.
// The switches belong to you (every phone of yours follows them); "on for
// this phone" is about this phone only.
function Notifications() {
  const [data, setData] = useState<NotifySettings | null>(null)
  const [state, setState] = useState<AlertState>(alertState)
  const [busy, setBusy] = useState<'on' | 'test' | null>(null)
  const [msg, setMsg] = useState<Msg>(null)

  useEffect(() => {
    getNotify()
      .then((r) => r?.settings && setData(r)) // (an older server has no /notifications)
      .catch((err) => setMsg(failed(err)))
  }, [])

  async function turnOn() {
    if (!data?.web) return
    setBusy('on')
    setMsg(null)
    try {
      const now = await turnOnAlerts(data.web) // asks the phone first, straight from this tap
      setState(now)
      if (now === 'on') {
        setData({ ...data, devices: Math.max(data.devices, 1) })
        setMsg({ text: 'Alerts are on. Try “Send a test”.', tone: 'muted' })
      }
    } catch (err) {
      setMsg(failed(err))
    }
    setBusy(null)
  }

  async function flip(kind: AlertKind) {
    if (!data) return
    const before = data
    const on = !data.settings[kind]
    setData({ ...data, settings: { ...data.settings, [kind]: on } }) // at once; put back if it fails
    try {
      await setNotify({ [kind]: on })
    } catch (err) {
      setData(before)
      setMsg(failed(err))
    }
  }

  async function test() {
    setBusy('test')
    setMsg(null)
    try {
      const r = await sendTestAlert()
      setMsg(r.devices === 0 ? { text: 'No phone has alerts on yet. Turn them on first.', tone: 'warn' }
        : r.sent > 0 ? { text: `Sent to ${r.sent === 1 ? 'your phone' : `${r.sent} phones`}. It should arrive in a few seconds.`, tone: 'muted' }
          : { text: 'Couldn’t reach your phone. Turn alerts on again on it.', tone: 'warn' })
    } catch (err) {
      setMsg(failed(err))
    }
    setBusy(null)
  }

  const ready = data?.web && data.configured // the server is set up to send
  return (
    <>
      <div className="set-group">
        <div className="set-row is-static">
          <span className="set-icon"><BellIcon /></span>
          <span className="set-label">
            Alerts
            <span className="set-sub">{data && !ready ? 'Not set up on the server yet' : STATE_LINE[state]}</span>
          </span>
          {state === 'on' ? (
            <span className="pill pill-good">On</span>
          ) : state === 'off' && ready ? (
            <button className="btn btn-primary btn-row" onClick={turnOn} disabled={busy !== null}>
              {busy === 'on' ? 'Turning on…' : 'Turn on'}
            </button>
          ) : null}
        </div>
        {ALERTS.map((a) => (
          <div className="set-row is-static" key={a.kind}>
            <span className="set-icon">{a.icon}</span>
            <span className="set-label">
              {a.label}
              <span className="set-sub">{a.sub}</span>
            </span>
            <Switch label={a.label} on={data?.settings[a.kind] ?? true} disabled={!data} onFlip={() => flip(a.kind)} />
          </div>
        ))}
      </div>
      <p className="set-note">
        Prices are checked every morning. Nothing arrives between 10 pm and 8 am: it waits until morning.
        {state === 'blocked' && ' To allow alerts again: your phone’s Settings → Notifications → OnTrack.'}
      </p>
      {(state === 'on' || (data?.devices ?? 0) > 0) && ready && (
        <button className="btn btn-secondary set-test" onClick={test} disabled={busy !== null}>
          {busy === 'test' ? 'Sending…' : 'Send a test'}
        </button>
      )}
      <Message text={msg} />
    </>
  )
}

function Switch({ label, on, disabled, onFlip }: { label: string; on: boolean; disabled?: boolean; onFlip: () => void }) {
  return (
    <button className={on ? 'switch is-on' : 'switch'} role="switch" aria-checked={on} aria-label={label}
      disabled={disabled} onClick={onFlip}>
      <span className="switch-knob" />
    </button>
  )
}

// ------------------------------------------------------------------ profile

function NameForm({ me, onSaved }: { me: Me; onSaved: (me: Me) => void }) {
  const [name, setName] = useState(me.name)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<Msg>(null)

  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMsg(null)
    try {
      onSaved(await updateMe({ name }))
      setMsg({ text: 'Saved.', tone: 'muted' })
    } catch (err) {
      setMsg(failed(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="acct-form" onSubmit={save}>
      <input className="field" aria-label="Your name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
      <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      <Message text={msg} />
    </form>
  )
}

// ------------------------------------------------------------------- region

function RegionForm({ me, onSaved }: { me: Me; onSaved: (me: Me) => void }) {
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
      onSaved(await updateMe({ country, currency, timezone: zone }))
      setMsg({ text: 'Saved.', tone: 'muted' })
    } catch (err) {
      setMsg(failed(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="acct-form" onSubmit={save}>
      <p className="budget-note">Prices show in your currency; “this month” follows your time zone. OnTrack doesn’t convert currencies.</p>
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
      <Message text={msg} />
    </form>
  )
}

// ------------------------------------------------------------------ devices

function Devices({ onCount }: { onCount: (n: number) => void }) {
  const [tokens, setTokens] = useState<TokenInfo[] | null>(null)
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null)
  const [msg, setMsg] = useState<Msg>(null)

  const load = () =>
    listTokens()
      .then((list) => {
        setTokens(list)
        onCount(list.filter((t) => t.kind !== 'session').length)
      })
      .catch((err) => setMsg(failed(err)))
  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, when the row opens
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
    <div className="acct-part">
      <p className="budget-note">Each Shortcut and the browser extension gets its own key. Lost a phone? Remove its key here.</p>
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
    </div>
  )
}

// ------------------------------------------------------------ people (owner)

function People() {
  const [people, setPeople] = useState<Person[]>([])
  const [invites, setInvites] = useState<Invite[]>([])
  const [note, setNote] = useState('')
  const [fresh, setFresh] = useState<{ label: string; link: string } | null>(null)
  const [msg, setMsg] = useState<Msg>(null)
  const [armed, setArmed] = useState<number | null>(null) // "Remove" tapped once: the next tap removes

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

  // Remove access: two taps, like Delete. They're signed out everywhere at
  // once and can't log in; their list stays, so Give access back undoes it.
  async function remove(p: Person) {
    if (armed !== p.id) {
      setArmed(p.id)
      return
    }
    setArmed(null)
    setMsg(null)
    try {
      await removeAccess(p.id)
      setMsg({ text: `${p.name} can’t use OnTrack now and was signed out everywhere. Their list is kept.`, tone: 'muted' })
      await load()
    } catch (err) {
      setMsg(failed(err))
    }
  }

  async function restore(p: Person) {
    setMsg(null)
    try {
      await restoreAccess(p.id)
      setMsg({ text: `${p.name} can log in again with their password. Their Shortcuts need a new key.`, tone: 'muted' })
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
    <div className="acct-part">
      <p className="budget-note">OnTrack is invite-only. An invite works once, for 7 days; a reset link for 2.</p>
      {fresh && <Reveal label={fresh.label} value={fresh.link} hint="Send this link yourself (message or email). It works once." />}
      <ul className="acct-list">
        {people.map((p) => (
          <li key={p.id} className={p.removed_at ? 'acct-row is-removed' : 'acct-row'}>
            <div className="acct-row-text">
              <span className="acct-row-name">
                {p.name}
                {p.is_admin && <span className="tag">Owner</span>}
                {p.removed_at && <span className="tag tag-warn">Removed</span>}
              </span>
              <span className="budget-note">{p.email} · {p.items} {p.items === 1 ? 'item' : 'items'}</span>
            </div>
            <div className="acct-row-actions">
              {p.removed_at ? (
                <button className="btn btn-quiet" onClick={() => restore(p)}>Give access back</button>
              ) : (
                <>
                  <button className="btn btn-quiet" onClick={() => reset(p)}>Reset link</button>
                  {!p.is_admin && (
                    <button className={armed === p.id ? 'btn btn-quiet is-armed' : 'btn btn-quiet'}
                      onClick={() => remove(p)} onBlur={() => setArmed(null)}>
                      {armed === p.id ? 'Tap to remove' : 'Remove'}
                    </button>
                  )}
                </>
              )}
            </div>
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
    </div>
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
    <form className="acct-form" onSubmit={save}>
      <input className="field" type="password" aria-label="Current password" placeholder="Current password"
        autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
      <input className="field" type="password" aria-label="New password" placeholder="New password (10+ characters)"
        autoComplete="new-password" minLength={10} required value={next} onChange={(e) => setNext(e.target.value)} />
      <button className="btn btn-primary" type="submit">Change password</button>
      <Message text={msg} />
    </form>
  )
}

// ---------------------------------------------------------------- connection

// The server address: only needed for local development (the deployed app
// knows its server), so it stays small and closed at the bottom.
function Connection({ onSaved }: { onSaved: () => Promise<void> }) {
  const [server, setServer] = useState(getServer())
  async function save(e: FormEvent) {
    e.preventDefault()
    saveServer(server)
    await onSaved()
  }
  return (
    <details className="auth-server set-server">
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
