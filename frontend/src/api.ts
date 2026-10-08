// Every request to the backend goes through this file.
// Components never build URLs or headers themselves; they call
// getSummary(), patchItem() and so on.

import type { Item, RefreshResult, Status, Summary } from './types'

const SERVER_KEY = 'ontrack.server'
const API_KEY_KEY = 'ontrack.apiKey'

// Where to find the server and which key to send. The browser's saved
// settings win; otherwise fall back to frontend/.env.local (development).
export function getSettings() {
  return {
    server: localStorage.getItem(SERVER_KEY) || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000',
    apiKey: localStorage.getItem(API_KEY_KEY) || import.meta.env.VITE_API_KEY || '',
  }
}

export function saveSettings(server: string, apiKey: string) {
  localStorage.setItem(SERVER_KEY, server.trim().replace(/\/+$/, ''))
  localStorage.setItem(API_KEY_KEY, apiKey.trim())
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { server, apiKey } = getSettings()
  let response: Response
  try {
    response = await fetch(server + path, {
      ...options,
      headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new Error(`Can't reach the server at ${server}. Is uvicorn running?`)
  }

  if (response.status === 204) return undefined as T // e.g. DELETE: nothing to read
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) throw new Error('The API key was rejected. Check it in Settings.')
    const detail = body && typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return body as T
}

export const getSummary = () => request<Summary>('/summary')

export const addFromLink = (url: string) =>
  request<Item>('/items/from-link', { method: 'POST', body: JSON.stringify({ url }) })

// Add by hand: a name and a price, and optionally a store link (saved
// without contacting the store; Refresh can fill in the store's price later).
export const addManual = (name: string, price: number, url?: string) =>
  request<Item>('/items', { method: 'POST', body: JSON.stringify(url ? { name, price, url } : { name, price }) })

export const patchItem = (id: number, fields: { status?: Status; name?: string; purchased_price?: number }) =>
  request<Item>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(fields) })

// Re-check prices on the server (every store except Amazon, which the iPhone does).
export const refreshPrices = () => request<RefreshResult>('/refresh', { method: 'POST' })

export const deleteItem = (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' })

export const setBudget = (amount: number) =>
  request<{ budget: number }>('/budget', { method: 'PUT', body: JSON.stringify({ amount }) })