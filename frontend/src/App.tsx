import { useEffect, useState } from 'react'
import { Offline, SIGNED_OUT, addFromLink, deleteItem, getMe, getSummary, getToken, patchItem, refreshPrices, save, saved } from './api'
import type { Item, Me, Summary } from './types'
import BudgetCard from './components/BudgetCard'
import Tabs, { type TabId } from './components/Tabs'
import ItemList from './components/ItemList'
import type { RowAction } from './components/ItemRow'
import AccountSheet from './components/AccountSheet'
import AuthScreen, { type AuthMode } from './components/AuthScreen'
import { MoneyProvider } from './money'
import { MoonIcon, PlusIcon, RefreshIcon, SlidersIcon, SunIcon } from './components/Icons'
import { refreshNote } from './format'
import { useTheme } from './hooks/useTheme'
import AddLink from './components/AddLink'
import AddByHand from './components/AddByHand'
import AddSheet from './components/AddSheet'
import { usePhone } from './hooks/usePhone'

// An invite or reset link opens the app as /?invite=CODE or /?reset=CODE.
function linkFromUrl(): { mode: AuthMode; code: string } | null {
  const params = new URLSearchParams(window.location.search)
  const invite = params.get('invite')
  const reset = params.get('reset')
  if (invite) return { mode: 'signup', code: invite }
  if (reset) return { mode: 'reset', code: reset }
  return null
}

// Android: sharing a product to the installed app opens it as
// /?title=…&text=…&url=… (the share_target in manifest.webmanifest). Apps put
// the link in different places (often inside "text"), so take the first web
// address found. It's kept until the list is on screen, even across a log-in.
const SHARED_KEY = 'ontrack.shared'

function takeSharedLink() {
  const params = new URLSearchParams(window.location.search)
  if (!params.has('url') && !params.has('text')) return
  const found = [params.get('url'), params.get('text'), params.get('title')]
    .map((v) => v?.match(/https?:\/\/\S+/)?.[0])
    .find(Boolean)
  if (found) sessionStorage.setItem(SHARED_KEY, found)
  window.history.replaceState(null, '', window.location.pathname) // a reload shouldn't add it twice
}
takeSharedLink()

// "10:42" today, "12 Oct, 10:42" before today.
function savedWhen(iso: string): string {
  const d = new Date(iso)
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return d.toDateString() === new Date().toDateString() ? time : `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })}, ${time}`
}

// Who is using the app decides what it shows: the sign-in screen, or their list.
export default function App() {
  const [signedIn, setSignedIn] = useState(() => !!getToken())
  const [link, setLink] = useState(linkFromUrl)
  const [me, setMe] = useState<Me | null>(null)

  // Any request that finds this login has ended (api.ts) brings us back here,
  // and the list is cleared from the screen.
  useEffect(() => {
    const onSignedOut = () => {
      setSignedIn(false)
      setMe(null)
    }
    window.addEventListener(SIGNED_OUT, onSignedOut)
    return () => window.removeEventListener(SIGNED_OUT, onSignedOut)
  }, [])

  useEffect(() => {
    if (!signedIn) return
    getMe()
      .then((user) => {
        setMe(user)
        save('me', user)
      })
      .catch((e) => {
        // Offline: use the saved profile, so prices keep the right currency.
        // (A 401 has already signed out; other errors show on the list.)
        if (e instanceof Offline) setMe(saved<Me>('me')?.value ?? null)
      })
  }, [signedIn])

  function changeMe(user: Me) {
    setMe(user)
    save('me', user)
  }

  function handleSignedIn(user: Me) {
    window.history.replaceState(null, '', window.location.pathname) // drop ?invite=… so a reload doesn't reuse it
    setLink(null)
    changeMe(user)
    setSignedIn(true)
  }

  if (!signedIn || link) {
    return <AuthScreen mode={link?.mode ?? 'login'} code={link?.code ?? ''} onSignedIn={handleSignedIn} />
  }
  return (
    <MoneyProvider currency={me?.currency ?? 'INR'} country={me?.country ?? 'IN'}>
      <WishList me={me} onMe={changeMe} />
    </MoneyProvider>
  )
}

function WishList({ me, onMe }: { me: Me | null; onMe: (me: Me) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('planned')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [note, setNote] = useState<{ text: string; tone: 'muted' | 'warn' } | null>(null)
  const [offlineSince, setOfflineSince] = useState<string | null>(null) // set: showing the saved copy
  const [adding, setAdding] = useState(false) // the phone's add sheet
  const theme = useTheme()
  const phone = usePhone()

  // Fetch the latest numbers and items (on opening, after a button press,
  // on coming back). Each good answer is saved; with no connection, the
  // saved copy is shown instead, read-only.
  async function load() {
    try {
      const fresh = await getSummary()
      setSummary(fresh)
      save('summary', fresh)
      setError(null)
      setOfflineSince(null)
    } catch (e) {
      const copy = saved<Summary>('summary')
      if (e instanceof Offline && copy) {
        setSummary(copy.value)
        setOfflineSince(copy.at)
        setError(null)
      } else {
        setError((e as Error).message)
      }
    }
  }

  // First load, when the page opens. If something was shared to the app
  // (Android), add it first, then load.
  useEffect(() => {
    const shared = sessionStorage.getItem(SHARED_KEY)
    sessionStorage.removeItem(SHARED_KEY)
    if (!shared) {
      load()
      return
    }
    setNote({ text: 'Adding the shared link…', tone: 'muted' })
    addFromLink(shared)
      .then((item) => {
        setTab('planned')
        setNote(addedNote(item))
      })
      .catch((e: Error) => setNote({ text: e.message, tone: 'warn' }))
      .finally(load)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, on opening
  }, [])

  // Coming back to the app (from Shortcuts, another app or another tab), or
  // the connection coming back: reload, so prices the iPhone refreshed in
  // the meantime show up.
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === 'visible') load()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('online', load)
    return () => {
      document.removeEventListener('visibilitychange', onVisible) // clean up when the app closes
      window.removeEventListener('online', load)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load only uses setters
  }, [])

  // The note under the header fades away after a few seconds.
  useEffect(() => {
    if (!note) return
    const timer = setTimeout(() => setNote(null), 6000)
    return () => clearTimeout(timer)
  }, [note])

  // The refresh button: the server re-checks prices, then we reload.
  async function handleRefresh() {
    setRefreshing(true)
    setNote(null)
    try {
      const result = await refreshPrices()
      await load()
      setNote({ text: refreshNote(result), tone: 'muted' })
    } catch (e) {
      setNote({ text: (e as Error).message, tone: 'warn' })
    } finally {
      setRefreshing(false)
    }
  }

  // A row button was pressed: tell the server, then reload so the budget
  // card, counts and lists all reflect the change.
  async function handleAction(item: Item, action: RowAction) {
    if (offlineSince) {
      setNote({ text: 'You’re offline. Changes need a connection.', tone: 'warn' })
      return
    }
    try {
      if (action === 'delete') await deleteItem(item.id)
      else await patchItem(item.id, { status: action })
      await load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const items = summary?.items ?? []
  const counts = {
    planned: items.filter((i) => i.status === 'planned').length,
    later: items.filter((i) => i.status === 'later').length,
    purchased: items.filter((i) => i.status === 'purchased').length,
    all: items.length,
  }

  // After adding an item (by link or by hand): new items start on the
  // wish list, so switch to that tab and reload. On the phone the add sheet
  // closes, and the note under the header says what happened.
  async function showNewItem(item: Item) {
    setTab('planned')
    if (phone) {
      setAdding(false)
      setNote(addedNote(item))
    }
    await load()
  }

  const visible = tab === 'all' ? items : items.filter((i) => i.status === tab)

  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="brand">OnTrack</div>
          <div className="eyebrow">{me ? `${me.name.split(' ')[0]}’s wish list` : 'Your wish list, on budget'}</div>
        </div>
        <div className="header-actions">
          <button
            className={refreshing ? 'icon-btn is-spinning' : 'icon-btn'}
            aria-label="Refresh prices"
            title="Refresh prices"
            disabled={refreshing || !!offlineSince}
            onClick={handleRefresh}
          >
            <RefreshIcon />
          </button>
          <button
            className="icon-btn"
            aria-label={theme.isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            onClick={() => theme.setPref(theme.isDark ? 'light' : 'dark')}
          >
            {theme.isDark ? <SunIcon /> : <MoonIcon />}
          </button>
          <button className="icon-btn" aria-label="Open account" onClick={() => setSettingsOpen(true)} disabled={!me}>
            <SlidersIcon />
          </button>
        </div>
      </header>
      {offlineSince && (
        <p className="offline-note" role="status">
          <i className="dot dot-offline" />
          Offline · showing your list from {savedWhen(offlineSince)}
        </p>
      )}
      {note && (
        <p className={note.tone === 'warn' ? 'header-note is-warn' : 'header-note'} role="status">
          {note.text}
        </p>
      )}

      <div className="columns">
        <aside className="side">
          {error && <p className="notice notice-error">{error}</p>}
          {!error && !summary && <p className="notice">Loading…</p>}
          {summary && <BudgetCard summary={summary} onBudgetSaved={load} />}
          {summary && !phone && <AddLink onAdded={showNewItem} />}
          {summary && !phone && <AddByHand onAdded={showNewItem} />}
        </aside>

        <main className="main">
          <Tabs active={tab} counts={counts} onChange={setTab} />
          {/* key={tab}: a new tab means a fresh list, which replays the fade-in */}
          {summary && (
            <div key={tab} className="fade-in">
              <ItemList items={visible} tab={tab} onAction={handleAction} />
            </div>
          )}
        </main>
      </div>

      {phone && summary && !offlineSince && (
        <button className="fab" aria-label="Add something" onClick={() => setAdding(true)}>
          <PlusIcon />
        </button>
      )}
      {adding && <AddSheet onClose={() => setAdding(false)} onAdded={showNewItem} />}

      {settingsOpen && me && (
        <AccountSheet
          me={me}
          onClose={() => setSettingsOpen(false)}
          onChanged={(updated) => {
            onMe(updated)
            load() // "this month" may have moved with a new time zone
          }}
          onServerChanged={load}
        />
      )}
    </div>
  )
}

// What the note under the header says after an add.
function addedNote(item: Item): { text: string; tone: 'muted' | 'warn' } {
  return item.needs_price
    ? { text: `Added “${item.name}”, but couldn’t read its price yet.`, tone: 'warn' }
    : { text: `Added “${item.name}”.`, tone: 'muted' }
}
