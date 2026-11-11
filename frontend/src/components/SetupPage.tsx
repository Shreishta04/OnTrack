import { useEffect, useState, type ReactNode } from 'react'
import { createToken, getSetup } from '../api'
import type { SetupLinks } from '../types'
import { useEdgeBack } from '../hooks/useEdgeBack'
import {
  SHORTCUT_NAME, canInstall, connectLink, device, install, installed, markPhoneSetUp, onInstallOffer, phoneSetUp,
} from '../device'
import { AddBoxIcon, BackIcon, CheckIcon, ShareIcon } from './Icons'

interface SetupPageProps {
  notes: ReactNode
  onBack: () => void
}

// /setup: "Set up this phone". Different steps on an iPhone, an Android
// phone or a computer, so a friend can do it without editing anything.
export default function SetupPage({ notes, onBack }: SetupPageProps) {
  const edgeBack = useEdgeBack(onBack)
  const kind = device()

  return (
    <div className="page settings-page setup-steps-page" {...edgeBack}>
      <div className="settings-top">
        <button className="icon-btn" aria-label="Back" onClick={onBack}>
          <BackIcon />
        </button>
      </div>
      <h1 className="settings-title">Set up this phone</h1>
      {notes}
      {kind === 'iphone' && <IPhoneSteps />}
      {kind === 'android' && <AndroidSteps />}
      {kind === 'computer' && <ComputerSteps />}
    </div>
  )
}

// ------------------------------------------------------------------ pieces

function Step({ n, done, title, children }: { n: number; done?: boolean; title: string; children: ReactNode }) {
  return (
    <section className={done ? 'card step is-done' : 'card step'} aria-label={`Step ${n}: ${title}`}>
      <div className="step-head">
        <span className="step-num" aria-hidden="true">{done ? <CheckIcon /> : n}</span>
        <h2 className="step-title">{title}</h2>
        {done && <span className="pill pill-good">Done</span>}
      </div>
      <div className="step-body">{children}</div>
    </section>
  )
}

// ------------------------------------------------------------------ iPhone

function IPhoneSteps() {
  const [links, setLinks] = useState<SetupLinks | null>(null)
  const [linksProblem, setLinksProblem] = useState(false)
  const [got, setGot] = useState(false) // tapped "Get the Shortcut" on this visit
  const [connected, setConnected] = useState(phoneSetUp)
  const [key, setKey] = useState<string | null>(null) // only kept for "copy it instead"
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const home = installed()

  useEffect(() => {
    getSetup()
      .then(setLinks)
      .catch(() => setLinksProblem(true))
  }, [])

  // Makes this phone its own key, then opens the Shortcut once with it. The
  // Shortcut sees "ontrack-key:…", saves the key in a file on the phone and
  // says "OnTrack is connected". From then on nothing ever opens Shortcuts.
  async function connect() {
    setBusy(true)
    setProblem(null)
    try {
      const fresh = await createToken('iPhone Shortcuts')
      setKey(fresh.token)
      markPhoneSetUp()
      setConnected(true)
      window.location.href = connectLink(fresh.token)
    } catch (e) {
      setProblem((e as Error).message)
    }
    setBusy(false)
  }

  async function copyKey() {
    if (!key) return
    try {
      await navigator.clipboard.writeText(key)
      setCopied(true)
    } catch {
      setProblem('Couldn’t copy. Press and hold the key to copy it.')
    }
  }

  return (
    <>
      <p className="setup-lead">
        Three steps, once. Then <b>Share → {SHORTCUT_NAME}</b> works from Safari, Amazon and most shopping apps,
        with prices read by your phone.
      </p>

      <Step n={1} done={home} title="Add OnTrack to your Home Screen">
        {home ? (
          <p className="budget-note">You opened OnTrack from the Home Screen. Nothing to do.</p>
        ) : (
          <ol className="how-list">
            <li>Open this page in <b>Safari</b>.</li>
            <li>Tap <span className="glyph"><ShareIcon /></span> <b>Share</b> at the bottom of the screen.</li>
            <li>Scroll down, tap <span className="glyph"><AddBoxIcon /></span> <b>Add to Home Screen</b>, then <b>Add</b>.</li>
            <li>Open OnTrack from its new icon and come back here (Settings → Set up this phone).</li>
          </ol>
        )}
      </Step>

      <Step n={2} title="Get the Shortcuts">
        {linksProblem && <p className="notice notice-error">Couldn’t load the links. Check your connection and open this page again.</p>}
        {links && !links.add_shortcut_url && (
          <p className="notice">The Shortcuts aren’t shared yet. Ask the person who invited you.</p>
        )}
        {links?.add_shortcut_url && (
          <>
            <p className="budget-note">Each opens in the Shortcuts app: tap <b>Add Shortcut</b>, then come back.</p>
            <div className="step-actions">
              <a className="btn btn-primary" href={links.add_shortcut_url} onClick={() => setGot(true)}>
                Get “{SHORTCUT_NAME}”
              </a>
              {links.refresh_shortcut_url && (
                <a className="btn btn-secondary" href={links.refresh_shortcut_url}>
                  Get “Refresh OnTrack”
                </a>
              )}
            </div>
            {links.refresh_shortcut_url && (
              <p className="budget-note">Refresh OnTrack is optional: it checks Amazon prices from your phone.</p>
            )}
          </>
        )}
      </Step>

      <Step n={3} done={connected} title="Connect">
        <p className="budget-note">
          OnTrack makes a key for this phone and hands it to the Shortcut. The Shortcuts app opens once and asks to{' '}
          <b>Allow</b> saving it; you’ll see <b>“OnTrack is connected”</b>. Then come back here.
        </p>
        <div className="step-actions">
          <button className={connected ? 'btn btn-secondary' : 'btn btn-primary'} onClick={connect} disabled={busy}>
            {busy ? 'Connecting…' : connected ? 'Connect again' : 'Connect'}
          </button>
        </div>
        {!got && !connected && <p className="budget-note">Do step 2 first, so the Shortcut is there to connect.</p>}
        {problem && <p className="notice notice-error">{problem}</p>}
        {key && (
          <details className="key-fallback">
            <summary>The Shortcut didn’t open?</summary>
            <p className="budget-note">
              Check it’s called exactly “{SHORTCUT_NAME}”, then tap Connect again. Or copy this key and paste it
              into the Shortcut when it asks:
            </p>
            <code className="key-text">{key}</code>
            <button className="btn btn-secondary" onClick={copyKey}>{copied ? 'Copied' : 'Copy the key'}</button>
          </details>
        )}
      </Step>

      <Step n={4} title="Try it">
        <ol className="how-list">
          <li>Open any product in Safari or a shopping app.</li>
          <li>Tap <span className="glyph"><ShareIcon /></span> <b>Share</b> → scroll the list → <b>{SHORTCUT_NAME}</b>.</li>
          <li>A notification says <b>“Added to OnTrack · … · ₹…”</b>.</li>
        </ol>
        <p className="budget-note">
          To keep it near the top: at the bottom of that list, <b>Edit Actions…</b> → tap the green <b>+</b> next to it.
        </p>
      </Step>
    </>
  )
}

// ------------------------------------------------------------------ Android

function AndroidSteps() {
  const [offer, setOffer] = useState(canInstall)
  const [home, setHome] = useState(installed)

  useEffect(() => onInstallOffer(() => setOffer(true)), [])

  async function tapInstall() {
    if (await install()) {
      markPhoneSetUp()
      setHome(true)
    }
    setOffer(canInstall())
  }

  return (
    <>
      <p className="setup-lead">
        On Android, OnTrack itself appears in the <b>Share</b> menu once it’s installed. No Shortcuts, no keys.
      </p>
      <Step n={1} done={home} title="Install OnTrack">
        {home ? (
          <p className="budget-note">OnTrack is installed on this phone.</p>
        ) : offer ? (
          <div className="step-actions">
            <button className="btn btn-primary" onClick={tapInstall}>Install OnTrack</button>
          </div>
        ) : (
          <ol className="how-list">
            <li>Open this page in <b>Chrome</b>.</li>
            <li>Tap <b>⋮</b> (top right) → <b>Install app</b> or <b>Add to Home screen</b> → <b>Install</b>.</li>
          </ol>
        )}
      </Step>
      <Step n={2} title="Try it">
        <ol className="how-list">
          <li>Open any product in Chrome or a shopping app.</li>
          <li>Tap <b>Share</b> → <b>OnTrack</b>. The item opens in OnTrack, with its price.</li>
        </ol>
      </Step>
    </>
  )
}

// ------------------------------------------------------------------ computer

function ComputerSteps() {
  return (
    <>
      <p className="setup-lead">
        On a computer, paste links into OnTrack, or add the <b>OnTrack browser extension</b>: it saves the page your
        browser already shows, so Amazon and stores that block servers work too.
      </p>
      <Step n={1} title="On your phone">
        <p className="budget-note">Open OnTrack on your phone and go to Settings → <b>Set up this phone</b>.</p>
      </Step>
      <Step n={2} title="Browser extension (Chrome or Edge)">
        <ol className="how-list">
          <li>Settings → <b>Shortcuts and extension</b> → make a key called “Laptop”.</li>
          <li>Load the extension (see the README), open its settings and paste the key.</li>
        </ol>
      </Step>
    </>
  )
}
