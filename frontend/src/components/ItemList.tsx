import type { ReactNode } from 'react'
import type { Item, PeriodInfo } from '../types'
import type { TabId } from './Tabs'
import ItemRow, { type RowAction } from './ItemRow'
import Price from './Price'
import { localDay, periodName, periodOf } from '../format'

const EMPTY: Record<TabId, [string, string]> = {
  planned: ['Nothing on your wish list', 'Paste a link or share one from your phone.'],
  later: ['Nothing parked', 'Move things here when they can wait.'],
  purchased: ['Nothing bought yet', 'Mark an item as bought and it lands here.'],
  all: ['Your list is empty', 'Add your first link to get started.'],
}

interface ItemListProps {
  items: Item[]
  tab: TabId
  onAction: (item: Item, action: RowAction) => Promise<void>
  picked: Set<number> // ticked item ids (every tab can tick)
  onPick: (item: Item) => void
  query?: string // what's typed in the search bar, if it's open
  period?: PeriodInfo // this budget period (Bought is grouped by period)
  zone?: string // the person's time zone: which day a purchase falls on
  oldestFirst?: boolean // the list is sorted oldest first
}

export default function ItemList({ items, tab, onAction, picked, onPick, query, period, zone, oldestFirst }: ItemListProps) {
  const row = (item: Item) => (
    <ItemRow
      key={item.id}
      item={item}
      showTag={tab === 'all'}
      onAction={onAction}
      picked={picked.has(item.id)}
      onPick={() => onPick(item)}
    />
  )

  // Bought: one quiet heading per budget period, with what was spent in it,
  // so it's clear why "Spent" only counts this period.
  if (tab === 'purchased' && period && zone && !query && items.length > 0) {
    return <BoughtByPeriod items={items} period={period} zone={zone} row={row} oldestFirst={!!oldestFirst} />
  }

  if (items.length === 0) {
    const [title, text] = query ? ['No matches', `Nothing here matches “${query}”.`] : EMPTY[tab]
    return (
      <div className="empty">
        <div className="empty-title">{title}</div>
        <div className="empty-text">{text}</div>
      </div>
    )
  }

  return (
    <div className="list" role="tabpanel">
      {items.map(row)}
    </div>
  )
}

interface Group {
  start: string
  end: string
  items: Item[]
}

function BoughtByPeriod({ items, period, zone, row, oldestFirst }: {
  items: Item[]
  period: PeriodInfo
  zone: string
  row: (item: Item) => ReactNode
  oldestFirst: boolean
}) {
  const resetDay = period.reset_day ?? 1
  // Keep the sort order the person chose: a period's heading goes where its
  // first item is. This period is always shown, even with nothing in it.
  const groups: Group[] = []
  const current: Group = { start: period.starts_on, end: period.ends_on, items: [] }
  for (const item of items) {
    const day = item.purchased_at ? localDay(item.purchased_at, zone) : period.starts_on
    const inCurrent = day >= period.starts_on && day <= period.ends_on
    const p = inCurrent ? current : periodOf(day, resetDay)
    let group = inCurrent ? current : groups.find((g) => g.start === p.start)
    if (!group) {
      group = { ...p, items: [] }
      groups.push(group)
    }
    if (!groups.includes(group)) groups.push(group)
    group.items.push(item)
  }
  if (!groups.includes(current)) {
    // nothing bought this period yet: its heading still goes first (last when oldest first)
    if (oldestFirst) groups.push(current)
    else groups.unshift(current)
  }

  return (
    <div className="list" role="tabpanel">
      {groups.map((g) => {
        const total = g.items.reduce((sum, i) => sum + (i.purchased_price ?? 0), 0)
        const label = g === current ? `This period · ${periodName(g)}` : periodName(g)
        return (
          <section className="period-group" key={g.start} aria-label={label}>
            <h3 className="period-head">
              <span>{label}</span>
              <Price amount={total} />
            </h3>
            {g.items.length === 0
              ? <p className="period-empty">Nothing bought yet this period.</p>
              : g.items.map(row)}
          </section>
        )
      })}
    </div>
  )
}
