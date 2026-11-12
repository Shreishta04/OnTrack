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
