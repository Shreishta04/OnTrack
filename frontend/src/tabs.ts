// The four lists, left to right. Shared by the tabs (labels), and by the
// app (which way to slide, where a swipe goes next).
export type TabId = 'planned' | 'later' | 'purchased' | 'all'

export const TABS: { id: TabId; label: string }[] = [
  { id: 'planned', label: 'Wish list' },
  { id: 'later', label: 'Later' },
  { id: 'purchased', label: 'Bought' },
  { id: 'all', label: 'All' },
]

export const TAB_ORDER: TabId[] = TABS.map((t) => t.id)
