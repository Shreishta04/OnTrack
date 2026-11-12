// OnTrack's service worker: a small script the browser keeps running in the
// background for this site. It lets the app OPEN without a connection, by
// keeping a copy of the app's own files (the page, its JavaScript and CSS,
// the icons).
//
// It never touches requests to the server (Railway): your list is saved by
// the app itself (api.ts), and requests with your login token are never
// stored here.
//
// Rules:
//   the page itself   the saved copy first, so the app opens at once, even
//                     on a slow phone connection; a fresh copy is fetched in
//                     the background for next time. (A new version is still
//                     noticed straight away: useNewVersion asks Vercel itself
//                     and shows "A new version is ready · Update".) Every
//                     address (/, /settings) is the same single page, so the
//                     one saved copy opens any of them.
//   /assets/…         saved copy first (Vite gives every build new file
//                     names, so a saved file never goes out of date)
//   anything else     straight to the network
//
// It also shows OnTrack's alerts (price drops, reminders): the server sends
// them through Firebase as a small message, and the "push" handler at the
// bottom turns it into a notification, even when the app is closed.

const CACHE = 'ontrack-app-v1'
// (same name as before on purpose: the copy already saved on phones keeps working)

// Find the /assets/… files a page uses, so they can be saved with it.
const assetsIn = (html) => [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((m) => m[1])

// Save the page and its files, and forget files from older versions.
async function savePage(response) {
  const cache = await caches.open(CACHE)
  const html = await response.clone().text()
  const keep = new Set(assetsIn(html))
  await cache.put('/', response)
  await Promise.all([...keep].map(async (path) => (await cache.match(path)) || cache.add(path)))
  for (const request of await cache.keys()) {
    const path = new URL(request.url).pathname
    if (path.startsWith('/assets/') && !keep.has(path)) await cache.delete(request)
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(CACHE)
      await cache.addAll(['/manifest.webmanifest', '/icon-192.png', '/favicon-64.png'])
      await savePage(await fetch('/', { cache: 'no-store' }))
      await self.skipWaiting() // use this version straight away
    })(),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      for (const name of await caches.keys()) if (name !== CACHE) await caches.delete(name)
      await self.clients.claim() // look after pages that are already open
    })(),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return // the server, fonts: not ours

  if (request.mode === 'navigate') {
    // Fetch a fresh copy in the background either way, and save it.
    const fresh = fetch(request).then((response) => {
      if (response.ok) event.waitUntil(savePage(response.clone()))
      return response
    })
    event.waitUntil(fresh.catch(() => {})) // offline: nothing to save, and that's fine
    event.respondWith(
      (async () => {
        const saved = await caches.match('/')
        if (saved) return saved // open at once with the saved copy
        try {
          return await fresh // the very first visit: nothing saved yet
        } catch {
          return Response.error()
        }
      })(),
    )
    return
  }

  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      (async () => {
        const saved = await caches.match(request)
        if (saved) return saved
        const response = await fetch(request)
        if (response.ok) {
          const cache = await caches.open(CACHE)
          event.waitUntil(cache.put(request, response.clone()))
        }
        return response
      })(),
    )
  }
})

// ------------------------------------------------------------------ alerts

// A message from the server (through Firebase): { data: { title, body, url, tag } }.
// Every push must show a notification (iPhones turn alerts off otherwise).
self.addEventListener('push', (event) => {
  let message = {}
  try {
    const payload = event.data ? event.data.json() : {}
    message = payload.data || payload.notification || payload
  } catch {
    message = { body: event.data ? event.data.text() : '' }
  }
  event.waitUntil(
    self.registration.showNotification(message.title || 'OnTrack', {
      body: message.body || '',
      icon: '/icon-192.png',
      badge: '/favicon-64.png',
      tag: message.tag || undefined, // the same news replaces itself instead of stacking up
      data: { url: message.url || '/' },
    }),
  )
})

// Tapping an alert: back to OnTrack if it's open, otherwise open it.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = new URL(event.notification.data?.url || '/', self.location.origin).href
  event.waitUntil(
    (async () => {
      const open = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      const app = open.find((c) => new URL(c.url).origin === self.location.origin)
      if (app) {
        await app.focus()
        return
      }
      await self.clients.openWindow(url)
    })(),
  )
})
