// How the list is ordered. The browser already has every item, so sorting
// happens here, instantly, with no request to the server.
import type { Item } from './types'

export type SortId = 'newest' | 'oldest' | 'price-low' | 'price-high'

export const SORTS: { id: SortId; label: string }[] = [
  { id: 'newest', label: 'Newest first' },
  { id: 'oldest', label: 'Oldest first' },
  { id: 'price-low', label: 'Price: low to high' },
  { id: 'price-high', label: 'Price: high to low' },
]

// The choice is remembered on this device (like light/dark mode), so the app
// opens the way it was left. Private browsing may block storage: then it
// simply starts at "Newest first" each time.
const STORAGE_KEY = 'ontrack.sort'

export function savedSort(): SortId {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return SORTS.some((s) => s.id === value) ? (value as SortId) : 'newest'
  } catch {
    return 'newest'
  }
}

export function saveSort(sort: SortId) {
  try {
    localStorage.setItem(STORAGE_KEY, sort)
  } catch {
    /* not remembered, that's all */
  }
}

// The price a row shows: what you paid, once bought; otherwise today's price.
export function shownPrice(item: Item): number | null {
  return item.status === 'purchased' ? item.purchased_price : item.price
}

// The date that counts as "new": when you bought it, for bought items (so
// something saved in August but bought today is on top), otherwise when it
// was added.
function when(item: Item): number {
  return Date.parse((item.status === 'purchased' && item.purchased_at) || item.created_at)
}

// A sorted copy (the original list is left as it is). Ties go newest first.
// Items with no price always sit at the bottom, in both price orders:
// otherwise "low to high" would open with a pile of blanks.
export function sortItems(items: Item[], sort: SortId): Item[] {
  return [...items].sort((a, b) => {
    if (sort === 'newest') return when(b) - when(a) || b.id - a.id
    if (sort === 'oldest') return when(a) - when(b) || a.id - b.id

    const pa = shownPrice(a)
    const pb = shownPrice(b)
    if (pa == null || pb == null) return (pa == null ? 1 : 0) - (pb == null ? 1 : 0) || b.id - a.id
    return (sort === 'price-low' ? pa - pb : pb - pa) || b.id - a.id
  })
}
