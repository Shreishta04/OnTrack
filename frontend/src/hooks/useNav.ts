import { useEffect, useState } from 'react'

// Which page is showing, and which sheet (if any) is open on top of it,
// kept in the browser's history so the phone's Back (button or swipe)
// works like in any app:
//   Back with a sheet open    closes the sheet
//   Back on Settings or
//   Analytics                 returns to the list
//   Back on the list          leaves the app, as usual
//
// Every page or sheet we open adds one history entry ("pushState"); every
// close goes back one entry, the same thing the Back button does. So our own
// ✕ buttons and the phone's Back can never disagree.

export type Page = 'list' | 'settings' | 'analytics' | 'setup'
export type Layer = 'add' | 'budget' | 'search' | null

interface Entry {
  page: Page
  layer: Layer
  ours?: boolean // true: we added this entry, so going back stays in the app
}

const PATHS: Record<Page, string> = { list: '/', settings: '/settings', analytics: '/analytics', setup: '/setup' }

function pageFromPath(): Page {
  const path = window.location.pathname.replace(/\/+$/, '')
  return path === '/settings' ? 'settings' : path === '/analytics' ? 'analytics' : path === '/setup' ? 'setup' : 'list'
}

// What the browser's history says is on screen now.
function fromHistory(): Entry {
  const saved = window.history.state as Entry | null
  return saved?.page ? saved : { page: pageFromPath(), layer: null }
}

export function useNav() {
  const [entry, setEntry] = useState<Entry>(() => {
    const start: Entry = { page: pageFromPath(), layer: null }
    window.history.replaceState(start, '') // label the entry we opened on
    return start
  })

  // The phone's Back (or Forward): show whatever that history entry says.
  useEffect(() => {
    const onPop = () => setEntry(fromHistory())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function push(next: Entry) {
    window.history.pushState({ ...next, ours: true }, '', PATHS[next.page])
    setEntry(next)
  }

  // Close what's showing. Normally that's one step back in history. If the
  // app was opened straight on /settings or /analytics, there's no step to go back to, so
  // swap the entry for the list instead.
  function back(fallback: Entry) {
    if ((window.history.state as Entry | null)?.ours) {
      window.history.back()
    } else {
      window.history.replaceState(fallback, '', PATHS[fallback.page])
      setEntry(fallback)
    }
  }

  return {
    page: entry.page,
    layer: entry.layer,
    go: (page: Page) => {
      push({ page, layer: null })
      window.scrollTo(0, 0)
    },
    back: () => back({ page: 'list', layer: null }),
    open: (layer: Exclude<Layer, null>) => push({ page: entry.page, layer }),
    close: () => {
      if (entry.layer) back({ page: entry.page, layer: null })
    },
  }
}
