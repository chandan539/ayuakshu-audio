import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api, type ModelInfo, type SystemInfo } from '../services/api'

type Props = {
  modelReady: boolean
  onRefresh: () => Promise<void>
}

function formatGb(bytes: number) {
  return `${(bytes / (1024 ** 3)).toFixed(2)} GB`
}

export function ModelsPage({ modelReady, onRefresh }: Props) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [details, setDetails] = useState<Record<string, unknown> | null>(null)

  async function load() {
    const [m, s, v] = await Promise.all([
      api.models(),
      api.system(),
      api.validateModel('chatterbox'),
    ])
    setModels(m.models)
    setSystem(s)
    setDetails(v)
  }

  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [modelReady])

  async function installFromLocal() {
    setError(null)
    setMessage(null)
    setBusy(true)
    try {
      const selected = await open({
        directory: true,
        multiple: false,
        title: 'Select OfflineVoice-Models folder',
      })
      if (!selected || Array.isArray(selected)) return

      const validation = await api.validatePackage(selected)
      if (!validation.valid) {
        setError(String(validation.message || 'Invalid package'))
        return
      }

      const result = await api.installModel(selected)
      setMessage(result.message)
      await load()
      await onRefresh()
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

  async function revalidate() {
    setBusy(true)
    setError(null)
    try {
      const v = await api.validateModel('chatterbox')
      setDetails(v)
      setMessage(String(v.message || 'Validation complete'))
      await load()
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1 className="page-title">AI Models</h1>
      <p className="page-sub">Detect, validate, and install models locally. Generation never auto-downloads.</p>

      {system && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <strong>Mac detected</strong>
          <div className="stats">
            <span>Apple Silicon: {system.apple_silicon ? 'Yes' : 'No'}</span>
            <span>Memory: {system.memory_gb ?? '—'} GB</span>
            <span>Available storage: {system.disk_free_gb ?? '—'} GB</span>
          </div>
          <div className="muted" style={{ marginTop: 8 }}>
            TTS engine: Chatterbox Multilingual · Status:{' '}
            {modelReady ? 'Ready' : 'Not ready'}
          </div>
          {system.warning && (
            <div className="notice warn" style={{ marginTop: 12, marginBottom: 0 }}>
              {system.warning}
            </div>
          )}
        </div>
      )}

      {message && <div className="notice">{message}</div>}
      {error && <div className="notice danger">{error}</div>}

      <div className="list">
        {models.map((m) => (
          <div className="list-item" key={m.id}>
            <div>
              <strong>{m.name}</strong>
              <div className="muted">
                {m.kind.toUpperCase()} · {formatGb(m.size_bytes || 0)}
              </div>
              <div className="mono muted">{m.path}</div>
              {!!m.missing_required?.length && (
                <div className="notice danger" style={{ marginTop: 8, marginBottom: 0 }}>
                  Missing: {m.missing_required.join(', ')}
                </div>
              )}
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className={`badge ${m.installed ? '' : 'warn'}`}>{m.status}</span>
              <div className="muted" style={{ marginTop: 8 }}>
                {m.message || (m.installed ? '✓ Installed · ✓ Ready for offline use' : 'Not installed')}
              </div>
            </div>
          </div>
        ))}
      </div>

      {details && (
        <div className="panel" style={{ marginTop: 16 }}>
          <strong>Path validation</strong>
          <p className="muted">{String(details.message || '')}</p>
          <div className="btn-row">
            <button type="button" className="btn" disabled={busy} onClick={revalidate}>
              Re-validate model files
            </button>
          </div>
        </div>
      )}

      <div className="panel" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>Offline Model Package</h3>
        <p>
          Application installer and AI model installer are separate. The DMG stays small; models install once into local storage.
        </p>
        <p>
          <strong>Internet required:</strong> YES — first-time setup only (or never, with USB package)<br />
          <strong>After setup:</strong> Internet required: NO
        </p>
        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={installFromLocal}>
            {busy ? 'Working…' : 'Install from Offline Model Package'}
          </button>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Expected layout: <span className="mono">OfflineVoice-Models/tts/chatterbox/</span> +{' '}
          <span className="mono">manifest.json</span>. Optional:{' '}
          <span className="mono">whisper/small.pt</span>,{' '}
          <span className="mono">extras/pkuseg/</span>.
        </p>
      </div>
    </div>
  )
}
