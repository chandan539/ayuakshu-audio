import { useEffect, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { desktopDir, downloadDir } from '@tauri-apps/api/path'
import { api } from '../services/api'

function friendlyPath(p?: string | null) {
  if (!p) return ''
  return p.replace(/^\/Users\/[^/]+/, '~')
}

export function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown>>({})
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    api.settings().then(setSettings).catch(() => undefined)
  }, [])

  async function save(patch: Record<string, unknown>) {
    const next = await api.updateSettings(patch)
    setSettings(next)
    setMessage('Settings saved locally.')
  }

  async function pickExportFolder() {
    const selected = await open({
      directory: true,
      multiple: false,
      defaultPath: String(settings.export_directory || '') || undefined,
      title: 'Choose default export folder',
    })
    if (!selected || Array.isArray(selected)) return
    await save({ export_directory: selected })
  }

  async function useDesktop() {
    try {
      await save({ export_directory: await desktopDir() })
    } catch {
      setMessage('Could not resolve Desktop. Use Choose folder…')
    }
  }

  async function useDownloads() {
    try {
      await save({ export_directory: await downloadDir() })
    } catch {
      setMessage('Could not resolve Downloads. Use Choose folder…')
    }
  }

  async function clearTemp() {
    const res = await api.clearTemp()
    setMessage(`Cleared ${res.removed} temporary item(s).`)
  }

  return (
    <div>
      <h1 className="page-title">Settings</h1>
      <p className="page-sub">Offline-first defaults. Core features never depend on update checks.</p>
      {message && <div className="notice">{message}</div>}

      <div className="panel">
        <label className="field">
          <span>Offline Mode</span>
          <select
            value={settings.offline_mode ? '1' : '0'}
            onChange={(e) => save({ offline_mode: e.target.value === '1' })}
          >
            <option value="1">ON</option>
            <option value="0">OFF</option>
          </select>
        </label>

        <div className="grid-2" style={{ marginTop: 16 }}>
          <label className="field">
            <span>Default language</span>
            <select
              value={String(settings.default_language || 'hi')}
              onChange={(e) => save({ default_language: e.target.value })}
            >
              <option value="hi">Hindi</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className="field">
            <span>Voice clone mode</span>
            <select
              value={String(settings.clone_mode || 'fast')}
              onChange={(e) => save({ clone_mode: e.target.value })}
            >
              <option value="fast">Fast clone (your voice + speed)</option>
              <option value="quality">Best clone (your voice + quality)</option>
            </select>
          </label>
          <p className="muted" style={{ gridColumn: '1 / -1', margin: '4px 0 0' }}>
            Default for new jobs. You can still change it on the Text to Speech page per generate.
          </p>
          <label className="field">
            <span>Max characters per chunk</span>
            <select
              value={String(settings.max_chunk_chars || 360)}
              onChange={(e) => save({ max_chunk_chars: Number(e.target.value) })}
            >
              {[220, 280, 360, 420].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <p className="muted" style={{ gridColumn: '1 / -1', margin: '4px 0 0' }}>
            This does not shorten your episode. Long scripts stay one WAV/MP3; only internal
            pieces get smaller so a 20+ minute file can finish on 16 GB Macs. Use 220 if you
            see “MPS out of memory”.
          </p>
          <label className="field" style={{ gridColumn: '1 / -1' }}>
            <span>Default export folder</span>
            <div className="mono muted" style={{ marginBottom: 8 }}>
              {settings.export_directory
                ? friendlyPath(String(settings.export_directory))
                : 'Not set — Save As will open a folder picker (Desktop by default).'}
            </div>
            <div className="btn-row" style={{ marginTop: 0 }}>
              <button type="button" className="btn" onClick={() => void pickExportFolder()}>
                Choose folder…
              </button>
              <button type="button" className="btn" onClick={() => void useDesktop()}>
                Use Desktop
              </button>
              <button type="button" className="btn" onClick={() => void useDownloads()}>
                Use Downloads
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => void save({ export_directory: '' })}
              >
                Ask every time
              </button>
            </div>
          </label>
          <label className="field">
            <span>MP3 Quality</span>
            <select
              value={String(settings.mp3_bitrate || 192)}
              onChange={(e) => save({ mp3_bitrate: Number(e.target.value) })}
            >
              {[128, 192, 256, 320].map((n) => (
                <option key={n} value={n}>{n} kbps</option>
              ))}
            </select>
          </label>
        </div>

        <div className="btn-row">
          <button type="button" className="btn" onClick={clearTemp}>
            Clear temporary files
          </button>
          <button type="button" className="btn" disabled title="Optional / manual only">
            Check for Updates — Manual (Coming Soon)
          </button>
        </div>
      </div>
    </div>
  )
}
