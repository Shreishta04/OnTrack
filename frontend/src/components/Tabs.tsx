import { useLayoutEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { TABS, TAB_ORDER, type TabId } from '../tabs'

export type { TabId }

interface TabsProps {
  active: TabId
  counts: Record<TabId, number>
  onChange: (tab: TabId) => void
}

// The tabs sit in a soft track; a raised pill marks the one you're on and
// glides to the next when you tap or swipe.
export default function Tabs({ active, counts, onChange }: TabsProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<{ left: number; width: number } | null>(null)

  // The tabs are as wide as their words ("Wish list 12" needs more room than
  // "All 30"), so the pill measures the active tab rather than assuming 25%.
  // It measures again whenever a tab changes size: a count going from 9 to
  // 10, the web font finishing loading, the phone turning sideways.
  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const place = () => {
      const tab = list.querySelector<HTMLElement>('[aria-selected="true"]')
      if (!tab) return
      const next = { left: tab.offsetLeft, width: tab.offsetWidth }
      setPill((now) => (now && now.left === next.left && now.width === next.width ? now : next))
    }
    place()
    const watch = new ResizeObserver(place)
    watch.observe(list)
    list.querySelectorAll('.tab').forEach((tab) => watch.observe(tab))
    document.fonts?.ready.then(place)
    return () => watch.disconnect()
  }, [active])

  // Left and right arrow keys move between tabs (the usual tab behaviour).
  function onKeyDown(e: KeyboardEvent) {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
    const next = TAB_ORDER[TAB_ORDER.indexOf(active) + step]
    if (!step || !next) return
    onChange(next)
    listRef.current?.querySelector<HTMLElement>(`[data-tab="${next}"]`)?.focus()
  }

  return (
    <div className="tabs" role="tablist" aria-label="Lists" ref={listRef} onKeyDown={onKeyDown}>
      {pill && (
        <div
          className="tab-pill"
          style={{ width: pill.width, transform: `translateX(${pill.left}px)` }}
          aria-hidden="true"
        />
      )}
      {TABS.map((tab) => (
        <button
          key={tab.id}
          className="tab"
          role="tab"
          data-tab={tab.id}
          aria-selected={tab.id === active}
          tabIndex={tab.id === active ? 0 : -1}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          <span className="tab-count">{counts[tab.id]}</span>
        </button>
      ))}
    </div>
  )
}
