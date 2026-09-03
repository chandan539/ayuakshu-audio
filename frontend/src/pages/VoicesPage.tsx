import { useEffect, useRef, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api, getBaseUrl, type Voice } from '../services/api'
import { startWavRecording, type RecorderHandle } from '../services/recorder'

type Props = {
  voices: Voice[]
  onRefresh: () => Promise<void>
}

export function VoicesPage({ voices, onRefresh }: Props) {
  const [name, setName] = useState(() => sessionStorage.getItem('ayu.voiceName') || 'My Voice')
  const [language, setLanguage] = useState(() => sessionStorage.getItem('ayu.voiceLang') || 'hi')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [busyLabel, setBusyLabel] = useState('Working…')
  const [recording, setRecording] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const recorderRef = useRef<RecorderHandle | null>(null)
  const tickRef = useRef<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    sessionStorage.setItem('ayu.voiceName', name)
  }, [name])

  useEffect(() => {
    sessionStorage.setItem('ayu.voiceLang', language)
  }, [language])

  useEffect(() => {
    return () => {
      if (tickRef.current) window.clearInterval(tickRef.current)
      audioRef.current?.pause()
    }
  }, [])

  function voiceAudioUrl(id: string) {
    return `${getBaseUrl()}/voices/${id}/audio`
  }

  async function playVoice(id: string) {
    setError(null)
    try {
      const url = voiceAudioUrl(id)
      if (!audioRef.current) {
        audioRef.current = new Audio()
      }
      const el = audioRef.current
      if (playingId === id && !el.paused) {
        el.pause()
        setPlayingId(null)
        return
      }
      el.src = url
      setPlayingId(id)
      el.onended = () => setPlayingId(null)
      el.onerror = () => {
        setPlayingId(null)
        setError('Could not play this voice file.')
      }
      await el.play()
    } catch (e) {
      setPlayingId(null)
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function importAudio() {
    setError(null)
    setMessage(null)
    setBusy(true)
    setBusyLabel('Choose an audio file…')
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'm4a', 'flac', 'aiff', 'aif'] }],
      })
      if (!selected || Array.isArray(selected)) {
        setBusy(false)
        return
      }
      setBusyLabel('Importing & normalizing (usually a few seconds)…')
      setMessage('Importing voice — decoding and preparing reference audio…')
      const voice = await api.createVoice({
        name: name.trim() || 'My Voice',
        language,
        source_audio: selected,
      })
      const quality = voice.metadata?.validation?.quality || 'Unknown'
      const warnings = voice.metadata?.validation?.warnings || []
      const secs = voice.metadata?.validation?.duration_sec
      setMessage(
        `Imported “${voice.name}”. Quality: ${quality}.` +
          (typeof secs === 'number' ? ` Duration: ${secs.toFixed(1)}s.` : '') +
          (warnings.length ? ` Notes: ${warnings.join(' ')}` : '') +
          ' Use Play to preview.',
      )
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setBusyLabel('Working…')
    }
  }

  async function toggleRecord() {
    setError(null)
    setMessage(null)
    if (!recording) {
      try {
        const handle = await startWavRecording()
        recorderRef.current = handle
        setRecording(true)
        setElapsed(0)
        tickRef.current = window.setInterval(() => {
          setElapsed(Math.floor((recorderRef.current?.elapsedMs() || 0) / 1000))
        }, 250)
        setMessage('Recording… speak clearly for 10–30 seconds, then press Stop & Save.')
      } catch (e) {
        const text = e instanceof Error ? e.message : String(e)
        if (/Permission|NotAllowed|denied/i.test(text)) {
          setError('Microphone permission denied. Allow mic access for AYUAKSHU Audio in System Settings.')
        } else {
          setError(text)
        }
      }
      return
    }

    setBusy(true)
    setBusyLabel('Saving recording…')
    setRecording(false)
    if (tickRef.current) {
      window.clearInterval(tickRef.current)
      tickRef.current = null
    }
    try {
      const handle = recorderRef.current
      recorderRef.current = null
      if (!handle) throw new Error('Recorder not active')
      const blob = await handle.stop()
      if (blob.size < 1000) {
        throw new Error('Recording too short — hold for a few seconds of speech.')
      }
      setBusyLabel('Normalizing recorded voice…')
      const voice = await api.uploadVoice({
        name: name.trim() || 'Recorded Voice',
        language,
        blob,
        filename: 'recording.wav',
      })
      const quality = voice.metadata?.validation?.quality || 'Unknown'
      setMessage(`Saved recorded voice “${voice.name}”. Quality: ${quality}. Use Play to preview.`)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
      setBusyLabel('Working…')
      setElapsed(0)
    }
  }

  async function remove(id: string) {
    if (playingId === id) {
      audioRef.current?.pause()
      setPlayingId(null)
    }
    await api.deleteVoice(id)
    await onRefresh()
  }

  return (
    <div>
      <h1 className="page-title">Voices</h1>
      <p className="page-sub">Import or record a reference voice. Audio stays on this Mac and is never uploaded.</p>

      <div className="notice">
        Only use voice recordings you own or have permission to use.
      </div>
      {busy && (
        <div className="notice">
          <strong>{busyLabel}</strong>
          <div className="progress-bar" style={{ marginTop: 8 }}>
            <span className="progress-indeterminate" />
          </div>
        </div>
      )}
      {message && <div className="notice">{message}</div>}
      {error && <div className="notice danger">{error}</div>}

      <div className="panel" style={{ marginBottom: 18 }}>
        <div className="grid-2">
          <label className="field">
            <span>Voice name</span>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span>Language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="hi">Hindi</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>
        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={busy || recording} onClick={importAudio}>
            {busy && !recording ? busyLabel : '+ Add Voice — Import Audio'}
          </button>
          <button
            type="button"
            className={recording ? 'btn btn-primary' : 'btn'}
            disabled={busy && !recording}
            onClick={toggleRecord}
          >
            {recording ? `Stop & Save (${elapsed}s)` : 'Record Voice'}
          </button>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Recommended: 10–30 seconds of clear speech, minimal background noise, single speaker.
          Supported import: WAV, MP3, M4A, FLAC. Record saves a local WAV via the mic.
        </p>
      </div>

      <div className="list">
        {voices.length === 0 && <div className="muted">No voices yet.</div>}
        {voices.map((v) => {
          const secs = v.metadata?.validation?.duration_sec
          return (
            <div className="list-item voice-item" key={v.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <strong>{v.name}</strong>
                <div className="muted">
                  {v.language.toUpperCase()} · {v.engine}
                  {v.metadata?.validation?.quality ? ` · ${v.metadata.validation.quality}` : ''}
                  {typeof secs === 'number' ? ` · ${secs.toFixed(1)}s` : ''}
                </div>
                <audio
                  className="voice-audio"
                  controls
                  preload="metadata"
                  src={voiceAudioUrl(v.id)}
                  onPlay={() => setPlayingId(v.id)}
                  onPause={() => setPlayingId((cur) => (cur === v.id ? null : cur))}
                >
                  <track kind="captions" />
                </audio>
              </div>
              <div className="btn-row" style={{ marginTop: 0, flexShrink: 0 }}>
                <button type="button" className="btn" onClick={() => playVoice(v.id)}>
                  {playingId === v.id ? 'Pause' : 'Play'}
                </button>
                <button type="button" className="btn" onClick={() => remove(v.id)}>
                  Delete
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
