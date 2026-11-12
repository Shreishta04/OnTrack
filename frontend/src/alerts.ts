// Turning on alerts on this phone.
//
// 1. The phone asks you: "OnTrack would like to send notifications". Browsers
//    only show that question after a tap, never on their own.
// 2. Firebase gives this phone a token: its address for alerts.
// 3. The token goes to the server (/push/devices), which sends alerts to it.
//
// On an iPhone this only works in the app opened from the Home Screen, not
// in a Safari tab (Apple's rule, iOS 16.4 and later).
//
// Firebase's code is only downloaded when you tap the button, so it never
// slows down opening the app.

import { addPushDevice } from './api'
import { device, installed } from './device'
import type { NotifySettings } from './types'

export type AlertState =
  | 'on' // this phone gets alerts
  | 'off' // can be turned on with a tap
  | 'blocked' // you said no; only the phone's Settings can undo that
  | 'home-screen' // iPhone in Safari: open the Home Screen app first
  | 'unsupported' // this browser can't get alerts

const KEY = 'ontrack:alerts-token'

export function alertState(): AlertState {
  if (device() === 'iphone' && !installed()) return 'home-screen'
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) return 'unsupported'
  if (Notification.permission === 'denied') return 'blocked'
  if (Notification.permission === 'granted' && savedToken()) return 'on'
  return 'off'
}

function savedToken(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export async function turnOnAlerts(web: NonNullable<NotifySettings['web']>): Promise<AlertState> {
  // Ask first, straight from the tap (Safari forgets the tap after an await).
  const answer = await Notification.requestPermission()
  if (answer === 'denied') return 'blocked'
  if (answer !== 'granted') return 'off'

  const registration = await navigator.serviceWorker.ready // our sw.js shows the alerts
  const [{ initializeApp, getApps }, { getMessaging, getToken }] = await Promise.all([
    import('firebase/app'),
    import('firebase/messaging'),
  ])
  const app = getApps()[0] ?? initializeApp(web.config)
  const token = await getToken(getMessaging(app), {
    vapidKey: web.vapid_key,
    serviceWorkerRegistration: registration,
  })
  if (!token) throw new Error('Firebase didn’t give this phone an address for alerts. Try again.')
  await addPushDevice(token, device())
  try {
    localStorage.setItem(KEY, token)
  } catch {
    // private mode: alerts still work, the button just shows "Turn on" again next time
  }
  return 'on'
}
