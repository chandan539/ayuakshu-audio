import { useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api } from '../services/api'

type Props = {
  onCompleted: () => Promise<void>
  onSkip: () => Promise<void>
}

export function SetupWizard({ onCompleted, onSkip }: Props) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [packagePath, setPackagePath] = useState<string | null>(null)

  async function choosePackage() {
    setError(null)
    setMessage(null)
    try {
      const selected = await open({ directory: true, multiple: false, title: 'Select OfflineVoice-Models folder' })
      if (!selected || Array.isArray(selected)) return
      setPackagePath(selected)
      setBusy(true)
      const validation = await api.validatePackage(selected)
      if (!validation.valid) {
        setError(String(validation.message || 'Invalid offline model package'))
        return
      }
      setMessage(
        `Package OK. Chatterbox size ~${(
          Number((validation.chatterbox as { size_bytes?: number })?.size_bytes || 0) /
          (1024 ** 3)
        ).toFixed(2)} GB` + (validation.pkuseg_included ? ' · pkuseg included' : ''),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function install() {
    if (!packagePath) {
      setError('Choose an OfflineVoice-Models folder first.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await api.installModel(packagePath)
      setMessage(result.message)
      await onCompleted()
    } catch (e) {
      const text = e instanceof Error ? e.message : String(e)
      if (/internet|offline|network/i.test(text)) {
        setError('Internet is unavailable. You can install the model from a local model package.')
      } else {
        setError(text)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="main" style={{ maxWidth: 720, margin: '0 auto' }}>
      <h1 className="page-title">Welcome to AYUAKSHU Audio</h1>
      <p className="page-sub">One-time AI model setup for fully offline Hindi + English voice TTS.</p>

      <div className="panel">
        <h2 style={{ marginTop: 0, fontFamily: 'var(--font-display)' }}>AI Model Setup</h2>
        <p>
          <strong>Chatterbox Multilingual</strong>
          <br />
          Required for Hindi + English voice TTS
        </p>
        <p className="muted">Model size: ~3 GB (plus optional tokenizer extras)</p>

        <div className="notice" style={{ marginTop: 12 }}>
          <div><strong>Internet required:</strong> YES — first-time setup only</div>
          <div><strong>After setup:</strong> Internet required: NO</div>
        </div>

        {message && <div className="notice">{message}</div>}
        {error && <div className="notice danger">{error}</div>}
        {packagePath && (
          <div className="mono muted" style={{ marginBottom: 12 }}>
            Selected: {packagePath}
          </div>
        )}

        <div className="btn-row">
          <button type="button" className="btn" disabled={busy} onClick={choosePackage}>
            Choose Offline Model Package
          </button>
          <button type="button" className="btn btn-primary" disabled={busy || !packagePath} onClick={install}>
            {busy ? 'Installing…' : 'Install Model'}
          </button>
          <button type="button" className="btn btn-ghost" disabled={busy} onClick={onSkip}>
            Skip for now
          </button>
        </div>

        <p className="muted" style={{ marginBottom: 0 }}>
          Air-gapped machines: copy <span className="mono">AYUAKSHU Audio.dmg</span> +{' '}
          <span className="mono">OfflineVoice-Models/</span> via USB. No Internet ever required.
          Build a package with <span className="mono">backend/scripts/pack_offline_models.py</span>.
        </p>
      </div>
    </div>
  )
}
