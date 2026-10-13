import { useEffect, useState } from 'react'

// True when the screen is phone-sized: the same width at which the two
// columns stack (index.css), so "phone layout" and "one column" always agree.
const QUERY = '(max-width: 860px)'

export function usePhone(): boolean {
  const [phone, setPhone] = useState(() => window.matchMedia(QUERY).matches)
  useEffect(() => {
    const media = window.matchMedia(QUERY)
    const onChange = () => setPhone(media.matches)
    media.addEventListener('change', onChange) // e.g. a tablet turned sideways
    return () => media.removeEventListener('change', onChange)
  }, [])
  return phone
}

// Opened from the home screen (installed), rather than in a browser tab.
export function isInstalled(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
}
