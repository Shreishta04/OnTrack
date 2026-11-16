import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './device' // catches Android's install offer before anything renders
import App from './App.tsx'
import CrashScreen from './components/CrashScreen'
import { reportCrashes } from './report'

reportCrashes() // problems the app runs into go to app.log, not the person's screen

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <CrashScreen>
      <App />
    </CrashScreen>
  </StrictMode>,
)

// The service worker (public/sw.js) lets the app open without a connection.
// Only in the built app: during development it would keep serving old files.
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {}) // the app works without it, just not offline
  })
}
