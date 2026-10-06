import type { Item } from '../types'
import type { TabId } from './Tabs'
import ItemRow, { type RowAction } from './ItemRow'

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
}

export default function ItemList({ items, tab, onAction }: ItemListProps) {
  if (items.length === 0) {
    const [title, text] = EMPTY[tab]
    return (
      <div className="empty">
        <div className="empty-title serif">{title}</div>
        <div className="empty-text">{text}</div>
      </div>
    )
  }

  return (
    <div className="list" role="tabpanel">
      {items.map((item) => (
        <ItemRow key={item.id} item={item} showTag={tab === 'all'} onAction={onAction} />
      ))}
    </div>
  )
}
