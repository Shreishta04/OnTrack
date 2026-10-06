import { useEffect, useState } from 'react'
import { getSummary } from './api'
import type { Summary } from './types'

export default function App() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch((e: Error) => setError(e.message))
  }, [])

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
          {summary && <p className="notice">Connected · {summary.items.length} items</p>}
        </aside>
        <main className="main">{/* tabs and item list go here */}</main>
      </div>
    </div>
  )
}