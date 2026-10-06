import { useEffect, useState } from 'react'

export type ThemePref = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'ontrack.theme'

function readSaved(): ThemePref {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved === 'light' || saved === 'dark' ? saved : 'system'
  } catch {
    return 'system'
  }
}

// Remembers the chosen theme and applies it to the page.
// "system" follows the device; "light"/"dark" override it.
export function useTheme() {
  const [pref, setPref] = useState<ThemePref>(readSaved)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)

  // Keep up if the device switches between light and dark while the app is open.
  useEffect(() => {
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  // Apply the choice: index.css reads the data-theme attribute on <html>.
  useEffect(() => {
    const root = document.documentElement
    if (pref === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', pref)
    try {
      localStorage.setItem(STORAGE_KEY, pref)
    } catch {
      /* private browsing: the choice just won't be remembered */
    }
  }, [pref])

  const isDark = pref === 'dark' || (pref === 'system' && systemDark)
  return { pref, setPref, isDark }
}