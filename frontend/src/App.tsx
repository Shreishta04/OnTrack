import { useEffect, useState } from 'react'
import { deleteItem, getSummary, patchItem, refreshPrices } from './api'
import type { Item, Summary } from './types'
import BudgetCard from './components/BudgetCard'
import Tabs, { type TabId } from './components/Tabs'
import ItemList from './components/ItemList'
import type { RowAction } from './components/ItemRow'
import SettingsSheet from './components/SettingsSheet'
import { MoonIcon, RefreshIcon, SlidersIcon, SunIcon } from './components/Icons'
import { refreshNote } from './format'
import { useTheme } from './hooks/useTheme'
import AddLink from './components/AddLink'
import AddByHand from './components/AddByHand'

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('planned')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [note, setNote] = useState<{ text: string; tone: 'muted' | 'warn' } | null>(null)
  const theme = useTheme()

  // Fetch the latest numbers and items again (after a button press).
  async function load() {
    try {
      setSummary(await getSummary())
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  // First load, when the page opens.
  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch((e: Error) => setError(e.message))
  }, [])

  // Coming back to the app (from Shortcuts, another app or another tab):
  // reload, so prices the iPhone refreshed in the meantime show up.
  useEffect(() => {
    function onVisible() {
      if (document.visibilityState !== 'visible') return
      getSummary()
        .then((s) => {
          setSummary(s)
          setError(null)
        })
        .catch((e: Error) => setError(e.message))
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible) // clean up when the app closes
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
  // wish list, so switch to that tab and reload.
  async function showNewItem() {
    setTab('planned')
    await load()
  }

  const visible = tab === 'all' ? items : items.filter((i) => i.status === tab)

  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="brand">OnTrack</div>
          <div className="eyebrow">Your wish list, on budget</div>
        </div>
        <div className="header-actions">
          <button
            className={refreshing ? 'icon-btn is-spinning' : 'icon-btn'}
            aria-label="Refresh prices"
            title="Refresh prices"
            disabled={refreshing}
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
          <button className="icon-btn" aria-label="Open settings" onClick={() => setSettingsOpen(true)}>
            <SlidersIcon />
          </button>
        </div>
      </header>
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
          {summary && <AddLink onAdded={showNewItem} />}
          {summary && <AddByHand onAdded={showNewItem} />}
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

      {settingsOpen && (
        <SettingsSheet onClose={() => setSettingsOpen(false)} onSaved={load} />
      )}
    </div>
  )
}