import { useEffect, useRef, useState } from 'react'
import { Offline, SIGNED_OUT, addFromLink, deleteItem, getMe, getSummary, getToken, patchItem, refreshPrices, save, saved } from './api'
import type { Item, Me, Status, Summary } from './types'
import BudgetCard from './components/BudgetCard'
import Tabs from './components/Tabs'
import { TAB_ORDER, type TabId } from './tabs'
import ListTools from './components/ListTools'
import { saveSort, savedSort, sortItems, type SortId } from './sort'
import { useSwipe } from './hooks/useSwipe'
import ItemList from './components/ItemList'
import type { ItemEdit, RowAction } from './components/ItemRow'
import SettingsPage from './components/SettingsPage'
import AnalyticsPage from './components/AnalyticsPage'
import BudgetSetup from './components/BudgetSetup'
import SetupPage from './components/SetupPage'
import { device, installed, markSetupLater, phoneSetUp, setupLater } from './device'
import BudgetSheet from './components/BudgetSheet'
import AuthScreen, { type AuthMode } from './components/AuthScreen'
import { MoneyProvider } from './money'
import { ChartIcon, CloseIcon, GearIcon, PlusIcon, RefreshIcon, SearchIcon } from './components/Icons'
import { displayName, refreshNote, storeName } from './format'
import { useTheme } from './hooks/useTheme'
import AddLink from './components/AddLink'
import AddByHand from './components/AddByHand'
import AddSheet from './components/AddSheet'
import SelectionBar, { type BulkAction } from './components/SelectionBar'
import { usePhone } from './hooks/usePhone'
import { useNewVersion } from './hooks/useNewVersion'
import { useNav } from './hooks/useNav'

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

// "Skip for now" on the budget setup screen is remembered on this device
// until the next log-in, so the screen doesn't come back on every visit (the
// reminder bar on the list stays until the budget and reset day are set).
// Browser storage can be blocked (private windows), hence the try/catch.
const SKIP_KEY = 'ontrack.setupSkipped'
function setupSkipped(): boolean {
  try {
    return localStorage.getItem(SKIP_KEY) === '1'
  } catch {
    return false
  }
}
function rememberSkip(skip: boolean) {
  try {
    if (skip) localStorage.setItem(SKIP_KEY, '1')
    else localStorage.removeItem(SKIP_KEY)
  } catch {
    // nothing to do: the setup screen just shows again next time
  }
}

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
  // Start with the profile saved on this device (if any), so the app can draw
  // straight away; the fresh one replaces it when the server answers.
  const [me, setMe] = useState<Me | null>(() => (getToken() ? (saved<Me>('me')?.value ?? null) : null))

  // Any request that finds this login has ended (api.ts) brings us back here,
  // and the list is cleared from the screen.
  useEffect(() => {
    const onSignedOut = () => {
      setSignedIn(false)
      setMe(null)
      window.history.replaceState(null, '', '/') // after logging in again, start on the list, not Settings
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
    rememberSkip(false) // a fresh log-in asks for the budget again, if it's still missing
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
  // Open instantly: show the list saved on this device while the server wakes
  // up (on the Free plan that can take several seconds), then swap in the
  // fresh one. `updating` is true until the first answer arrives.
  const [summary, setSummary] = useState<Summary | null>(() => saved<Summary>('summary')?.value ?? null)
  const [updating, setUpdating] = useState(() => saved<Summary>('summary') != null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('planned')
  const [refreshing, setRefreshing] = useState(false)
  const [note, setNote] = useState<{ text: string; tone: 'muted' | 'warn' } | null>(null)
  const [offlineSince, setOfflineSince] = useState<string | null>(null) // set: showing the saved copy
  const [picked, setPicked] = useState<Set<number>>(new Set()) // ticked items: a "what if", nothing saved
  const [sort, setSort] = useState<SortId>(savedSort) // the list order, remembered on this device
  // Which way the list slides in when the tab changes: from the right when
  // moving to a tab further right, from the left when going back.
  const [enter, setEnter] = useState<'fade-in' | 'slide-from-right' | 'slide-from-left'>('fade-in')
  const [query, setQuery] = useState('') // what's typed in the search bar
  const theme = useTheme()
  const phone = usePhone()
  const newVersion = useNewVersion()
  // The page (list or Settings) and the sheet on top of it, kept in the
  // browser's history so the phone's Back closes them (hooks/useNav.ts).
  const nav = useNav()
  const searching = nav.layer === 'search'
  const [skipped, setSkipped] = useState(setupSkipped)
  // "Set up this phone" reminder: phones only, until it's done or "Not now".
  // An Android phone with OnTrack installed is set up (it's in the Share menu).
  const [phoneLater, setPhoneLater] = useState(setupLater)
  const kind = device()
  const phoneNeedsSetup = kind !== 'computer' && !phoneSetUp() && !(kind === 'android' && installed()) && !phoneLater

  // Fetch the latest numbers and items (on opening, after a button press,
  // on coming back). Each good answer is saved; with no connection, the
  // saved copy is shown instead, read-only.
  // Counts changes shown on screen before the server answered (showNow). A
  // reload that started before the latest one is out of date when it comes
  // back: two quick moves would otherwise flicker the first item back.
  const changes = useRef(0)

  async function load() {
    const startedAt = changes.current
    try {
      const fresh = await getSummary()
      if (startedAt !== changes.current) return // a newer change is on screen; its own reload follows
      setSummary(fresh)
      save('summary', fresh)
      setError(null)
      setOfflineSince(null)
      setUpdating(false)
    } catch (e) {
      setUpdating(false)
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

  // While showing the saved copy, quietly try the server again every 20
  // seconds: a server waking from sleep, or signal coming back without the
  // phone announcing it, is picked up without anyone tapping anything.
  useEffect(() => {
    if (!offlineSince) return
    const timer = setInterval(load, 20_000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load only uses setters
  }, [offlineSince])

  const [retrying, setRetrying] = useState(false)
  async function retryNow() {
    setRetrying(true)
    await load()
    setRetrying(false)
  }

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

  // Show a change on screen straight away, before the server has answered:
  // the item moves (or goes) at once, and the reload that follows brings the
  // budget card and everything else exactly in line. If the server says no,
  // that reload puts things back the way they really are.
  function showNow(ids: number[], change: 'delete' | { status: Status } | { edit: ItemEdit }) {
    changes.current += 1
    setSummary((current) => {
      if (!current) return current
      const hit = new Set(ids)
      const items = change === 'delete'
        ? current.items.filter((i) => !hit.has(i.id))
        : current.items.map((i) => {
            if (!hit.has(i.id)) return i
            if ('status' in change) return { ...i, status: change.status }
            const e = change.edit
            const own = e.manual_price !== undefined && i.best_link_id == null // no store price: the typed one counts
            return {
              ...i,
              ...(e.name !== undefined && { name: e.name }),
              ...(e.note !== undefined && { note: e.note }),
              ...(e.purchased_price !== undefined && { purchased_price: e.purchased_price }),
              ...(own && { manual_price: e.manual_price ?? null, price: e.manual_price ?? null, needs_price: e.manual_price == null }),
            }
          })
      return { ...current, items }
    })
  }

  // A row button was pressed: show it at once, tell the server, then reload
  // so the budget card, counts and lists all reflect the change.
  async function handleAction(item: Item, action: RowAction) {
    if (offlineSince) {
      setNote({ text: 'You’re offline. Changes need a connection.', tone: 'warn' })
      return
    }
    showNow([item.id], action === 'delete' ? 'delete' : typeof action === 'object' ? action : { status: action })
    try {
      if (action === 'delete') await deleteItem(item.id)
      else if (typeof action === 'object') await patchItem(item.id, action.edit) // Edit, or a typed price
      else await patchItem(item.id, { status: action })
    } catch (e) {
      setNote({ text: `Couldn’t save that: ${(e as Error).message}`, tone: 'warn' })
    }
    await load() // the real numbers (and the real list, if the server refused)
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
      if (nav.layer === 'add') nav.close()
      setNote(addedNote(item))
    }
    await load()
  }

  // Search: keep items whose name or store contains what's typed (any
  // capitals). It searches the tab you're on; the counts stay the full ones.
  const words = searching ? query.trim().toLowerCase() : ''
  const matches = (i: Item) => !words || `${displayName(i)} ${storeName(i)}`.toLowerCase().includes(words)
  const visible = sortItems((tab === 'all' ? items : items.filter((i) => i.status === tab)).filter(matches), sort)

  function openSearch() {
    setQuery('')
    nav.open('search')
  }

  // Ticking belongs to one tab: switching tabs starts fresh.
  function changeTab(next: TabId) {
    if (next === tab) return
    setEnter(TAB_ORDER.indexOf(next) > TAB_ORDER.indexOf(tab) ? 'slide-from-right' : 'slide-from-left')
    setTab(next)
    setPicked(new Set())
  }

  // A flick on the phone: left shows the next tab, right the previous one.
  // At either end there's nowhere to go, so nothing happens.
  const swipe = useSwipe(
    () => {
      const next = TAB_ORDER[TAB_ORDER.indexOf(tab) + 1]
      if (next) changeTab(next)
    },
    () => {
      const prev = TAB_ORDER[TAB_ORDER.indexOf(tab) - 1]
      if (prev) changeTab(prev)
    },
  )

  function changeSort(next: SortId) {
    setSort(next)
    saveSort(next)
  }

  function togglePick(item: Item) {
    setPicked((now) => {
      const next = new Set(now)
      if (next.has(item.id)) next.delete(item.id)
      else next.add(item.id)
      return next
    })
  }

  // Only items still on this tab count (one may have moved meanwhile).
  const pickedItems = visible.filter((i) => picked.has(i.id))
  const allPicked = visible.length > 0 && pickedItems.length === visible.length

  // A button in the selection bar: move the ticked items (or, for "Park the
  // rest", every unticked wish-list item), one request each, then reload once.
  // Items already on the target list are left alone (on the All tab, "Mark
  // bought" with a bought item ticked mustn't touch it).
  async function handleBulk(action: BulkAction) {
    if (offlineSince) {
      setNote({ text: 'You’re offline. Changes need a connection.', tone: 'warn' })
      return
    }
    if (action === 'delete') {
      const n = pickedItems.length
      showNow(pickedItems.map((i) => i.id), 'delete')
      setPicked(new Set())
      try {
        await Promise.all(pickedItems.map((i) => deleteItem(i.id)))
        setNote({ text: `Deleted ${n} ${n === 1 ? 'item' : 'items'}.`, tone: 'muted' })
        setPicked(new Set())
      } catch (e) {
        setNote({ text: (e as Error).message, tone: 'warn' })
      }
      await load()
      return
    }
    const parkRest = action === 'park-rest'
    const status: Status = parkRest ? 'later' : action.move
    const targets = (parkRest ? visible.filter((i) => !picked.has(i.id)) : pickedItems)
      .filter((i) => i.status !== status)
    showNow(targets.map((i) => i.id), { status })
    setPicked(new Set())
    try {
      await Promise.all(targets.map((i) => patchItem(i.id, { status })))
      const n = targets.length
      const things = `${n} ${n === 1 ? 'item' : 'items'}`
      setNote({
        text: n === 0 ? 'Those are already there, so nothing moved.'
          : status === 'purchased' ? `Marked ${things} as bought.`
          : status === 'later' ? `Moved ${things} to Later.` : `Moved ${things} back to your wish list.`,
        tone: 'muted',
      })
      setPicked(new Set())
    } catch (e) {
      setNote({ text: (e as Error).message, tone: 'warn' })
    }
    await load()
  }

  const selecting = pickedItems.length > 0

  // The lines under the header: offline, a new version, what just happened.
  // Shown on both pages.
  const notes = (
    <>
      {updating && !offlineSince && (
        <p className="header-note updating-note" role="status">
          <i className="dot dot-update" /> Updating…
        </p>
      )}
      {offlineSince && (
        <button className="offline-note" role="status" onClick={retryNow} disabled={retrying}>
          <i className="dot dot-offline" />
          Offline · showing your list from {savedWhen(offlineSince)} ·{' '}
          <span className="note-action">{retrying ? 'Trying…' : 'Try again'}</span>
        </button>
      )}
      {newVersion && (
        <button className="offline-note update-note" onClick={() => window.location.reload()}>
          <i className="dot dot-update" />
          A new version of OnTrack is ready · <span className="note-action">Update</span>
        </button>
      )}
      {note && (
        <p className={note.tone === 'warn' ? 'header-note is-warn' : 'header-note'} role="status">
          {note.text}
        </p>
      )}
    </>
  )

  // The budget or the reset day isn't set yet. (period is missing only from
  // an older server: then there's nothing to ask for.)
  const period = summary?.period
  const needsSetup = !!period && (period.default_budget == null || period.reset_day == null)
  const reminder = !period ? '' : period.default_budget == null && period.reset_day == null
    ? 'Set your budget and reset day'
    : period.default_budget == null ? 'Set your monthly budget' : 'Pick the day your budget resets'

  if (nav.page === 'settings' && me) {
    return (
      <SettingsPage
        me={me}
        summary={summary}
        theme={theme}
        notes={notes}
        onBack={nav.back}
        onMe={(updated) => {
          onMe(updated)
          load() // "this month" may have moved with a new time zone
        }}
        onBudgetSaved={load}
        onServerChanged={load}
        onOpenSetup={() => nav.go('setup')}
      />
    )
  }

  if (nav.page === 'setup' && me) {
    return <SetupPage notes={notes} onBack={nav.back} />
  }

  if (nav.page === 'analytics' && me) {
    return <AnalyticsPage me={me} summary={summary} notes={notes} onBack={nav.back} />
  }

  // Just logged in, budget not set: ask for it before showing the list.
  // Not while offline (the saved copy can be out of date, and saving needs
  // a connection).
  if (needsSetup && !skipped && !offlineSince && period) {
    return (
      <BudgetSetup
        period={period}
        name={me?.name}
        onSaved={load}
        onSkip={() => {
          rememberSkip(true)
          setSkipped(true)
          window.scrollTo(0, 0)
        }}
      />
    )
  }

  const pageClass = ['page', selecting && 'has-bar', searching && 'is-searching'].filter(Boolean).join(' ')

  return (
    <div className={pageClass}>
      <header className="header">
        <div className="brand">OnTrack</div>
        <div className="header-actions">
          <button className="icon-btn" aria-label="Search your list" onClick={openSearch} disabled={!summary}>
            <SearchIcon />
          </button>
          {period && (
            <button className="icon-btn" aria-label="Analytics" title="Analytics" onClick={() => nav.go('analytics')} disabled={!me}>
              <ChartIcon />
            </button>
          )}
          <button
            className={refreshing ? 'icon-btn is-spinning' : 'icon-btn'}
            aria-label="Refresh prices"
            title="Refresh prices"
            disabled={refreshing || !!offlineSince}
            onClick={handleRefresh}
          >
            <RefreshIcon />
          </button>
          <button className="icon-btn" aria-label="Settings" onClick={() => nav.go('settings')} disabled={!me}>
            <GearIcon />
          </button>
        </div>
      </header>
      {!needsSetup && phoneNeedsSetup && !offlineSince && summary && (
        <div className="offline-note setup-note phone-note">
          <i className="dot dot-setup" />
          <span className="phone-note-text">
            Add products by sharing them ·{' '}
            <button className="link-btn note-action" onClick={() => nav.go('setup')}>Set up this phone</button>
          </span>
          <button
            className="link-btn phone-note-later"
            onClick={() => {
              markSetupLater()
              setPhoneLater(true)
            }}
          >
            Not now
          </button>
        </div>
      )}
      {needsSetup && !offlineSince && (
        <button className="offline-note setup-note" onClick={() => nav.open('budget')}>
          <i className="dot dot-setup" />
          {reminder} · <span className="note-action">Set it</span>
        </button>
      )}
      {notes}

      <div className="columns">
        <aside className="side">
          {error && <p className="notice notice-error">{error}</p>}
          {!error && !summary && <p className="notice">Loading…</p>}
          {summary && <BudgetCard summary={summary} onEdit={() => nav.open('budget')} />}
          {summary && !phone && <AddLink onAdded={showNewItem} />}
          {summary && !phone && <AddByHand onAdded={showNewItem} />}
        </aside>

        {/* the whole list area listens for flicks (on a phone) */}
        <main className="main" {...swipe}>
          {searching && (
            <div className="search-bar fade-in" role="search">
              <SearchIcon />
              <input
                className="search-input"
                type="search"
                aria-label="Search your list"
                placeholder="Search by name or store"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && nav.close()}
                autoFocus
              />
              <button className="icon-btn search-close" aria-label="Close search" onClick={nav.close}>
                <CloseIcon />
              </button>
            </div>
          )}
          <Tabs active={tab} counts={counts} onChange={changeTab} />
          {summary && visible.length > 0 && (
            <ListTools
              allPicked={allPicked}
              onSelectAll={() => setPicked(new Set(visible.map((i) => i.id)))}
              onClearAll={() => setPicked(new Set())}
              sort={sort}
              onSort={changeSort}
            />
          )}
          {/* key={tab}: a new tab means a fresh list, which replays the slide-in */}
          {summary && (
            <div key={tab} className={enter}>
              <ItemList items={visible} tab={tab} onAction={handleAction} picked={picked} onPick={togglePick}
                query={words ? query.trim() : undefined} />
            </div>
          )}
        </main>
      </div>

      {selecting && summary && (
        <SelectionBar
          tab={tab}
          picked={pickedItems}
          allPicked={allPicked}
          summary={summary}
          onAction={handleBulk}
          onClear={() => setPicked(new Set())}
        />
      )}
      {phone && summary && !offlineSince && !selecting && !searching && (
        <button className="fab" aria-label="Add something" onClick={() => nav.open('add')}>
          <PlusIcon />
        </button>
      )}
      {nav.layer === 'add' && <AddSheet onClose={nav.close} onAdded={showNewItem} />}
      {nav.layer === 'budget' && summary && (
        <BudgetSheet
          current={summary.budget}
          period={summary.period}
          onClose={nav.close}
          onSaved={async () => {
            await load()
            nav.close()
          }}
        />
      )}
    </div>
  )
}

// What the note under the header says after an add.
function addedNote(item: Item): { text: string; tone: 'muted' | 'warn' } {
  return item.needs_price
    ? { text: `Added “${displayName(item)}”, but couldn’t read its price yet.`, tone: 'warn' }
    : { text: `Added “${displayName(item)}”.`, tone: 'muted' }
}
