import { useEffect, useState } from 'react'

// Is there a newer version of the app on Vercel than the one on screen?
//
// Why this is needed: an installed app on a phone is often only paused in the
// background, not closed. Coming back to it shows the same page, so a new
// version (already downloaded by the service worker) isn't used until the app
// is closed fully, and people don't know to do that.
//
// How: each build gives the app's main file a new name (/assets/index-AbC123.js).
// When the app comes back into view (and every 15 minutes while it's open), ask
// Vercel for the page and compare that name with the one running now. Different
// means a new version: App shows "A new version is ready · Update", and Update
// reloads the page, which fetches it fresh.
const EVERY = 15 * 60 * 1000

const mainScript = (html: string) => html.match(/src="(\/assets\/index-[^"]+\.js)"/)?.[1] ?? null

export function useNewVersion(): boolean {
  const [newer, setNewer] = useState(false)

  useEffect(() => {
    if (!import.meta.env.PROD) return // the dev server has no built file names
    const running = mainScript(document.documentElement.outerHTML)
    if (!running) return

    async function check() {
      if (document.visibilityState !== 'visible' || !navigator.onLine) return
      try {
        const page = await fetch('/', { cache: 'no-store' }) // past the service worker's copy
        const latest = page.ok ? mainScript(await page.text()) : null
        if (latest && latest !== running) setNewer(true)
      } catch {
        // offline or Vercel unreachable: try again next time
      }
    }

    check()
    const timer = setInterval(check, EVERY)
    document.addEventListener('visibilitychange', check)
    window.addEventListener('online', check)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', check)
      window.removeEventListener('online', check)
    }
  }, [])

  return newer
}
