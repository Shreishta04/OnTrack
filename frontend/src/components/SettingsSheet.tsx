import { useEffect, useState, type FormEvent } from 'react'
import { getSettings, saveSettings } from '../api'
import { CloseIcon } from './Icons'

interface SettingsSheetProps {
  onClose: () => void
  onSaved: () => Promise<void>
}

// Connection settings: things you set once and rarely touch again.
export default function SettingsSheet({ onClose, onSaved }: SettingsSheetProps) {
  // Drafts: what's typed in the boxes. Nothing is saved until "Save".
  const [server, setServer] = useState(() => getSettings().server)
  const [apiKey, setApiKey] = useState(() => getSettings().apiKey)
  const [saving, setSaving] = useState(false)

  // Close with the Escape key.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  async function handleSave(e: FormEvent) {
    e.preventDefault() // stop the browser reloading the page, which forms do by default
    setSaving(true)
    saveSettings(server, apiKey)
    await onSaved() // reload with the new server/key; any error shows on the main screen
    onClose()
  }

  return (
    <div className="sheet-layer">
      <button className="scrim" aria-label="Close settings" onClick={onClose} />
      <section className="card sheet" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div className="sheet-head">
          <div>
            <h2 id="settings-title" className="serif sheet-title">Settings</h2>
            <p className="budget-note">How this app reaches your OnTrack server.</p>
          </div>
          <button className="icon-btn" aria-label="Close settings" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>

        <form className="sheet-body" onSubmit={handleSave}>
          <div className="field-group">
            <label className="eyebrow" htmlFor="api-key">API key</label>
            <input
              id="api-key"
              className="field"
              type="password"
              autoComplete="off"
              placeholder="Paste your key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div className="field-group">
            <label className="eyebrow" htmlFor="server">Server address</label>
            <input
              id="server"
              className="field"
              type="url"
              placeholder="http://127.0.0.1:8000"
              value={server}
              onChange={(e) => setServer(e.target.value)}
            />
          </div>

          <button className="btn btn-primary btn-wide" type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </form>
      </section>
    </div>
  )
}
