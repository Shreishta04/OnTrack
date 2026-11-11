// What kind of device this is, and installing the app on it.
//
// iPhone: only the person can add a web app to the Home Screen (Share → Add
// to Home Screen); websites can't do it for them. Android (Chrome): the
// browser offers an install prompt, which we catch and show behind our own
// "Install OnTrack" button.

export type Device = 'iphone' | 'android' | 'computer'

export function device(): Device {
  const ua = navigator.userAgent
  if (/iPhone|iPod/.test(ua) || (/iPad/.test(ua))) return 'iphone'
  if (/Android/.test(ua)) return 'android'
  return 'computer'
}

// Opened from the Home Screen (installed), not in a browser tab.
export function installed(): boolean {
  return (
    (navigator as Navigator & { standalone?: boolean }).standalone === true ||
    window.matchMedia?.('(display-mode: standalone)').matches === true
  )
}

// Chrome's install offer. It fires once, early, so main.tsx imports this file
// before anything renders and we keep the event until the button is tapped.
interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}
let offer: InstallEvent | null = null
const listeners = new Set<() => void>()

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault() // keep it for our button instead of Chrome's own mini-bar
  offer = e as InstallEvent
  listeners.forEach((fn) => fn())
})

export function canInstall(): boolean {
  return offer != null
}

export function onInstallOffer(fn: () => void): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// Shows Chrome's "Install OnTrack?" box. True if the person said yes.
export async function install(): Promise<boolean> {
  if (!offer) return false
  await offer.prompt()
  const { outcome } = await offer.userChoice
  offer = null
  return outcome === 'accepted'
}

// "This phone is set up" is remembered on the phone itself (it's about this
// device, not the account). Browser storage can be blocked, hence the try.
const DONE_KEY = 'ontrack.phoneSetUp'
const LATER_KEY = 'ontrack.phoneSetupLater'

function read(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}
function write(key: string, on: boolean) {
  try {
    if (on) localStorage.setItem(key, '1')
    else localStorage.removeItem(key)
  } catch {
    // nothing to do: the reminder just shows again next time
  }
}

export const phoneSetUp = () => read(DONE_KEY)
export const markPhoneSetUp = (on = true) => write(DONE_KEY, on)
export const setupLater = () => read(LATER_KEY)
export const markSetupLater = () => write(LATER_KEY, true)

// The Shortcut's name, exactly as it's called in the Shortcuts app, and the
// one-time link that hands it this phone's key ("ontrack-key:…"). The
// Shortcut sees the prefix, saves the key in a file and says it's connected.
export const SHORTCUT_NAME = 'Add to OnTrack'
export function connectLink(key: string): string {
  return `shortcuts://run-shortcut?name=${encodeURIComponent(SHORTCUT_NAME)}&input=text&text=${encodeURIComponent(`ontrack-key:${key}`)}`
}
