// Small helpers for turning raw data into friendly text.

import type { Item } from './types'

// "https://www.amazon.in/dp/…" → "Amazon"
export function storeName(item: Item): string {
  const url = item.links[0]?.url
  if (!url) return 'Added by hand'
  let host: string
  try {
    host = new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return 'Link'
  }
  if (host.includes('amazon') || host.includes('amzn')) return 'Amazon'
  if (host.includes('littlebox')) return 'Littlebox'
  if (host.includes('savana')) return 'Savana'
  const base = host.split('.')[0]
  return base.charAt(0).toUpperCase() + base.slice(1)
}

// "2026-10-05T11:56:46+00:00" → "5 Oct"
export function shortDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}
