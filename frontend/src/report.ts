// Telling the server about problems the app itself runs into (a crash, a
// request that failed before it reached the server), so they land in
// app.log next to everything else. The person never sees the technical
// part: they get a plain sentence, sometimes with a reference code.
//
// Quiet by design: a report that can't be sent is dropped, the same problem
// is only reported once per visit, and at most 20 per visit.

import { ApiError, Offline, getServer, getToken } from './api'

const sent = new Set<string>()
const MAX = 20

export async function reportProblem(where: string, error: unknown): Promise<string | null> {
  const err = error instanceof Error ? error : new Error(String(error))
  const message = `${err.name}: ${err.message}`.slice(0, 500)
  const key = `${where}|${message}`
  const token = getToken()
  if (!token || sent.has(key) || sent.size >= MAX) return null
  sent.add(key)
  try {
    const r = await fetch(getServer() + '/logs/app', {
      method: 'POST',
      headers: { 'X-API-Key': token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ where: where.slice(0, 100), message, detail: (err.stack ?? '').slice(0, 3000) || null }),
    })
    return r.ok ? ((await r.json()).ref ?? null) : null
  } catch {
    return null // offline: nothing to do
  }
}

// Crashes nobody caught: the page itself, or a promise nobody waited for.
export function reportCrashes() {
  window.addEventListener('error', (e) => void reportProblem('page error', e.error ?? e.message))
  window.addEventListener('unhandledrejection', (e) => void reportProblem('unhandled promise', e.reason))
}

// What to show the person for an error: the server's own sentence, or "no
// connection"; anything else is a problem in the app itself, so it's
// reported (app.log) and the person gets a plain sentence instead.
export function friendly(where: string, error: unknown): string {
  if (error instanceof ApiError || error instanceof Offline) return error.message
  void reportProblem(where, error)
  return 'Something went wrong in OnTrack. Try again; if it keeps happening, tell the person who invited you.'
}
