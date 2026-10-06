export type TabId = 'planned' | 'later' | 'purchased' | 'all'

const TABS: { id: TabId; label: string }[] = [
  { id: 'planned', label: 'Wish list' },
  { id: 'later', label: 'Later' },
  { id: 'purchased', label: 'Bought' },
  { id: 'all', label: 'All' },
]

interface TabsProps {
  active: TabId
  counts: Record<TabId, number>
  onChange: (tab: TabId) => void
}

export default function Tabs({ active, counts, onChange }: TabsProps) {
  const index = TABS.findIndex((t) => t.id === active)

  return (
    <div className="tabs" role="tablist" aria-label="Lists">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          className="tab"
          role="tab"
          aria-selected={tab.id === active}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
          <span className="tab-count">{counts[tab.id]}</span>
        </button>
      ))}
      {/* One underline that slides to the active tab (each tab is 25% wide) */}
      <div className="tab-underline" style={{ transform: `translateX(${index * 100}%)` }} aria-hidden="true">
        <span />
      </div>
    </div>
  )
}
