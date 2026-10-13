// Every request to the backend goes through this file.
// Components never build URLs or headers themselves; they call
// getSummary(), patchItem() and so on.
//
// Logging in gives this browser its own token, kept in localStorage and sent
// with every request (in the X-API-Key header, like the Shortcuts do).
// A header rather than a cookie, because Safari blocks cookies between the
// web app's site (Vercel) and the server's (Railway).

import type { AuthResult, DeviceToken, Invite, Item, Me, NewCode, Person, RefreshResult, Status, Summary, TokenInfo } from './types'

const SERVER_KEY = 'ontrack.server'
const TOKEN_KEY = 'ontrack.token'
const OLD_KEY = 'ontrack.apiKey' // the shared key from before Accounts

// Where to find the server. The browser's saved setting wins; otherwise
// VITE_API_URL (set on Vercel, or in frontend/.env.local for development).
export function getServer(): string {
  return localStorage.getItem(SERVER_KEY) || import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
}

export function saveServer(server: string) {
  const clean = server.trim().replace(/\/+$/, '')
  if (clean) localStorage.setItem(SERVER_KEY, clean)
  else localStorage.removeItem(SERVER_KEY) // empty: back to the default
}

export const getToken = () => localStorage.getItem(TOKEN_KEY)

function saveToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.removeItem(OLD_KEY) // the old shared key shouldn't linger in this browser
}

// Forget this browser's login and tell the app to show the sign-in screen.
export const SIGNED_OUT = 'ontrack:signed-out'
export function signOutLocally() {
  localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(SIGNED_OUT))
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const server = getServer()
  let response: Response
  try {
    response = await fetch(server + path, {
      ...options,
      headers: { 'X-API-Key': getToken() ?? '', 'Content-Type': 'application/json', ...options.headers },
    })
  } catch {
    throw new Error(`Can't reach the server at ${server}. Check your connection and try again.`)
  }

  if (response.status === 204) return undefined as T // e.g. DELETE: nothing to read
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
    // 401 on a normal request: this login has ended (logged out elsewhere,
    // password changed). On /auth/… it just means a wrong password.
    if (response.status === 401 && !path.startsWith('/auth/')) signOutLocally()
    throw new Error(detail)
  }
  return body as T
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

// ------------------------------------------------------------- accounts

async function keep(result: Promise<AuthResult>): Promise<Me> {
  const { token, user } = await result
  saveToken(token)
  return user
}

export const logIn = (email: string, password: string) =>
  keep(request<AuthResult>('/auth/login', post({ email, password })))

export interface SignUpForm {
  invite: string
  email: string
  password: string
  name: string
  currency: string
  country: string
  timezone: string
}
export const signUp = (form: SignUpForm) => keep(request<AuthResult>('/auth/signup', post(form)))

export const resetPassword = (code: string, password: string) =>
  keep(request<AuthResult>('/auth/reset', post({ code, password })))

export async function logOut() {
  try {
    await request<void>('/auth/logout', { method: 'POST' })
  } finally {
    signOutLocally() // even if the server can't be reached
  }
}

export const getMe = () => request<Me>('/me')

export const updateMe = (fields: Partial<Pick<Me, 'name' | 'currency' | 'country' | 'timezone'>>) =>
  request<Me>('/me', { method: 'PATCH', body: JSON.stringify(fields) })

export const changePassword = (current: string, next: string) =>
  request<void>('/me/password', post({ current, new: next }))

export const listTokens = () => request<TokenInfo[]>('/tokens')
export const createToken = (name: string) => request<DeviceToken>('/tokens', post({ name }))
export const revokeToken = (id: number) => request<void>(`/tokens/${id}`, { method: 'DELETE' })

// Owner only
export const listInvites = () => request<Invite[]>('/invites')
export const createInvite = (note: string) => request<NewCode>('/invites', post({ note: note || null }))
export const cancelInvite = (id: number) => request<void>(`/invites/${id}`, { method: 'DELETE' })
export const listPeople = () => request<Person[]>('/users')
export const createResetCode = (userId: number) => request<NewCode>(`/users/${userId}/reset`, { method: 'POST' })

// The link to send someone: this web app's address with the code on the end.
export const linkFor = (kind: 'invite' | 'reset', code: string) =>
  `${window.location.origin}/?${kind}=${encodeURIComponent(code)}`

// ------------------------------------------------------------ the list

export const getSummary = () => request<Summary>('/summary')

export const addFromLink = (url: string) => request<Item>('/items/from-link', post({ url }))

// Add by hand: a name and a price, and optionally a store link (saved
// without contacting the store; Refresh can fill in the store's price later).
export const addManual = (name: string, price: number, url?: string) =>
  request<Item>('/items', post(url ? { name, price, url } : { name, price }))

export const patchItem = (id: number, fields: { status?: Status; name?: string; purchased_price?: number }) =>
  request<Item>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(fields) })

// Re-check prices on the server (every store except Amazon, which the iPhone does).
export const refreshPrices = () => request<RefreshResult>('/refresh', { method: 'POST' })

export const deleteItem = (id: number) => request<void>(`/items/${id}`, { method: 'DELETE' })

export const setBudget = (amount: number) =>
  request<{ budget: number }>('/budget', { method: 'PUT', body: JSON.stringify({ amount }) })
