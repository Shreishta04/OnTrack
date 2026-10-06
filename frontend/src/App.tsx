import { useEffect, useState } from 'react'
import { getSummary } from './api'
import type { Summary } from './types'
import BudgetCard from './components/BudgetCard'
import Tabs, { type TabId } from './components/Tabs'
import ItemList from './components/ItemList'

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<TabId>('planned')

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch((e: Error) => setError(e.message))
  }, [])

  const items = summary?.items ?? []
  const counts = {
    planned: items.filter((i) => i.status === 'planned').length,
    later: items.filter((i) => i.status === 'later').length,
    purchased: items.filter((i) => i.status === 'purchased').length,
    all: items.length,
  }
  const visible = tab === 'all' ? items : items.filter((i) => i.status === tab)

  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="brand">OnTrack</div>
          <div className="eyebrow">Your wish list, on budget</div>
        </div>
      </header>

      <div className="columns">
        <aside className="side">
          {error && <p className="notice notice-error">{error}</p>}
          {!error && !summary && <p className="notice">Loading…</p>}
          {summary && <BudgetCard summary={summary} />}
        </aside>

        <main className="main">
          <Tabs active={tab} counts={counts} onChange={setTab} />
          {/* key={tab}: a new tab means a fresh list, which replays the fade-in */}
          {summary && (
            <div key={tab} className="fade-in">
              <ItemList items={visible} tab={tab} />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
