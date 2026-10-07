import { useEffect, useState } from 'react'
import { open, save } from '@tauri-apps/plugin-dialog'
import { desktopDir } from '@tauri-apps/api/path'
import { api } from '../services/api'

type Props = {
  jobId?: string | null
  wavPath?: string | null
  mp3Path?: string | null
  wavLabel?: string | null
  mp3Label?: string | null
  onMessage?: (text: string) => void
}

function inTauri() {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

function friendlyPath(p?: string | null) {
  if (!p) return ''
  return p.replace(/^\/Users\/[^/]+/, '~')
}

function stampName(ext: string) {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `AYUAKSHU-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.${ext}`
}

function joinPath(folder: string, name: string) {
  return `${folder.replace(/\/+$/, '')}/${name}`
}

export function AudioPlayer({ jobId, wavPath, mp3Path, wavLabel, mp3Label, onMessage }: Props) {
  const [busy, setBusy] = useState(false)
  const [exportFolder, setExportFolder] = useState('')

  useEffect(() => {
    api
      .settings()
      .then((s) => setExportFolder(String(s.export_directory || '')))
      .catch(() => undefined)
  }, [jobId])

  if (!wavPath && !mp3Path) return null

  async function preferredFolder() {
    if (exportFolder) return exportFolder
    try {
      return await desktopDir()
    } catch {
      return ''
    }
  }

  async function exportFile(format: 'wav' | 'mp3' | 'both') {
    if (!jobId) {
      onMessage?.('Generate speech first, then export.')
      return
    }
    setBusy(true)
    try {
      const folder = await preferredFolder()
      let destination: string | null = null
      if (format === 'both') {
        const selected = await open({
          directory: true,
          multiple: false,
          defaultPath: folder || undefined,
          title: 'Choose a folder for WAV and MP3',
        })
        if (!selected || Array.isArray(selected)) return
        destination = selected
      } else {
        const ext = format
        const selected = await save({
          defaultPath: folder ? joinPath(folder, stampName(ext)) : stampName(ext),
          title: format === 'wav' ? 'Save WAV as…' : 'Save MP3 as…',
          filters: [
            format === 'wav'
              ? { name: 'WAV audio', extensions: ['wav'] }
              : { name: 'MP3 audio', extensions: ['mp3'] },
          ],
        })
        if (!selected) return
        destination = selected
      }
      const result = await api.exportJob(jobId, { format, destination, reveal: true })
      setExportFolder(result.folder)
      onMessage?.(
        `Saved to ${friendlyPath(result.folder)}. Finder is showing the file.`,
      )
    } catch (e) {
      onMessage?.(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function showInFinder(format: 'wav' | 'mp3' = 'wav') {
    if (!jobId) return
    try {
      const result = await api.revealJob(jobId, format)
      onMessage?.(`Showing ${friendlyPath(result.path)} in Finder.`)
    } catch (e) {
      onMessage?.(e instanceof Error ? e.message : String(e))
    }
  }

  const workingCopy = wavLabel || mp3Label

  return (
    <div className="audio-box panel" style={{ padding: 16, marginTop: 16 }}>
      <strong>Generated audio</strong>
      {workingCopy && (
        <div className="muted" style={{ wordBreak: 'break-all' }}>
          Working copy (app library): {friendlyPath(workingCopy)}
        </div>
      )}
      {exportFolder && (
        <div className="muted">Last export folder: {friendlyPath(exportFolder)}</div>
      )}
      {wavPath && (
        <div>
          <div className="muted">WAV preview</div>
          <audio controls src={wavPath} />
        </div>
      )}
      {mp3Path && (
        <div>
          <div className="muted">MP3 preview</div>
          <audio controls src={mp3Path} />
        </div>
      )}
      <div className="btn-row" style={{ marginTop: 4 }}>
        {inTauri() && jobId ? (
          <>
            {wavPath && (
              <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void exportFile('wav')}>
                {busy ? 'Saving…' : 'Save WAV as…'}
              </button>
            )}
            {mp3Path && (
              <button type="button" className="btn" disabled={busy} onClick={() => void exportFile('mp3')}>
                Save MP3 as…
              </button>
            )}
            {wavPath && mp3Path && (
              <button type="button" className="btn" disabled={busy} onClick={() => void exportFile('both')}>
                Save both to folder…
              </button>
            )}
            <button type="button" className="btn btn-ghost" disabled={!jobId} onClick={() => void showInFinder('wav')}>
              Show in Finder
            </button>
          </>
        ) : (
          <>
            {wavPath && (
              <a className="btn" href={wavPath} download="AYUAKSHU.wav">
                Download WAV
              </a>
            )}
            {mp3Path && (
              <a className="btn" href={mp3Path} download="AYUAKSHU.mp3">
                Download MP3
              </a>
            )}
          </>
        )}
      </div>
    </div>
  )
}
