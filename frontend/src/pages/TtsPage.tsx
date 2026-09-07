import { useEffect, useMemo, useRef, useState } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { api, type Job, type Project, type Voice } from '../services/api'
import { ProgressBar } from '../components/ProgressBar'
import { AudioPlayer } from '../components/AudioPlayer'
import { getBaseUrl } from '../services/api'

type Props = {
  voices: Voice[]
  projects: Project[]
  onRefresh: () => Promise<void>
  modelReady: boolean
  initialProject?: Project | null
}

const DRAFT_KEY = 'ayu.ttsDraft'

function loadDraft(): Partial<{
  text: string
  language: 'hi' | 'en'
  voiceId: string
  projectId: string
  cloneMode: 'fast' | 'quality'
}> {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function countWords(text: string) {
  const parts = text.trim().split(/\s+/).filter(Boolean)
  return parts.length
}

function estimateMinutes(chars: number) {
  return Math.max(0.1, chars / 750)
}

/** Wall-clock after Fast mode (turbo sampling + 2-step vocoder). First load extra. */
function estimateGenMinutes(chars: number, mode: 'fast' | 'quality') {
  const audioMins = estimateMinutes(chars)
  // Fast = your voice, speed-first. Quality = same voice, closer clone, slower.
  return Math.max(0.2, audioMins * (mode === 'quality' ? 8 : 1.4))
}

function isLoadingStage(stage?: string | null) {
  if (!stage) return false
  const s = stage.toLowerCase()
  return s.includes('loading') || s.includes('preparing voice') || s.includes('model ready')
}

export function TtsPage({ voices, projects, onRefresh, modelReady, initialProject }: Props) {
  const draft = useRef(loadDraft()).current
  const [voiceId, setVoiceId] = useState(
    initialProject?.voice_id || draft.voiceId || voices[0]?.id || '',
  )
  const [language, setLanguage] = useState<'hi' | 'en'>(
    (initialProject?.language as 'hi' | 'en') || draft.language || 'hi',
  )
  const [text, setText] = useState(
    initialProject?.text ||
      draft.text ||
      'नमस्ते, मेरा नाम चंदन है।\nआज हम एक नए विषय के बारे में बात करेंगे।',
  )
  const [projectId, setProjectId] = useState<string>(initialProject?.id || draft.projectId || '')
  const [cloneMode, setCloneMode] = useState<'fast' | 'quality'>(draft.cloneMode || 'fast')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [modelLoaded, setModelLoaded] = useState(false)
  const [modelWarming, setModelWarming] = useState(false)
  const pollRef = useRef<number | null>(null)
  const appliedProject = useRef<string | null>(initialProject?.id || null)

  // Persist draft so tab switches / remounts keep the user's text.
  useEffect(() => {
    sessionStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ text, language, voiceId, projectId, cloneMode }),
    )
  }, [text, language, voiceId, projectId, cloneMode])

  useEffect(() => {
    if (!voiceId && voices[0]?.id) setVoiceId(voices[0].id)
  }, [voices, voiceId])

  // When user opens a project from Projects tab, apply it once.
  useEffect(() => {
    if (!initialProject?.id) return
    if (appliedProject.current === initialProject.id) return
    appliedProject.current = initialProject.id
    setProjectId(initialProject.id)
    setText(initialProject.text || '')
    setLanguage((initialProject.language as 'hi' | 'en') || 'hi')
    if (initialProject.voice_id) setVoiceId(initialProject.voice_id)
    setNotice(`Opened project “${initialProject.title}”.`)
  }, [initialProject])

  useEffect(() => {
    let cancelled = false
    async function pollHealth() {
      try {
        const h = await api.health()
        if (cancelled) return
        setModelLoaded(Boolean(h.model_loaded))
        setModelWarming(Boolean(h.model_warming))
      } catch {
        /* ignore */
      }
    }
    pollHealth()
    const id = window.setInterval(pollHealth, 2500)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // Restore in-flight or latest completed job after navigation.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const { job: active } = await api.activeJob()
        if (cancelled || !active) return
        setJob(active)
        if (active.status === 'queued' || active.status === 'running') {
          setBusy(true)
          startPolling(active.id)
        } else if (active.status === 'interrupted' || active.status === 'failed') {
          setNotice('Previous long job can continue. Click Resume to keep finished audio and finish the rest.')
        }
        if (active.text && !text.trim()) setText(active.text)
        if (active.voice_id) setVoiceId(active.voice_id)
        if (active.language === 'hi' || active.language === 'en') setLanguage(active.language)
        if (active.project_id) setProjectId(active.project_id)
      } catch {
        /* ignore */
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once on mount
  }, [])

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const stats = useMemo(() => {
    const chars = text.length
    const words = countWords(text)
    const mins = estimateMinutes(chars)
    const genMins = estimateGenMinutes(chars, cloneMode)
    return { chars, words, mins, genMins }
  }, [text, cloneMode])

  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  function startPolling(jobId: string) {
    stopPolling()
    const tick = async () => {
      try {
        const latest = await api.job(jobId)
        setJob(latest)
        if (['completed', 'failed', 'cancelled', 'interrupted'].includes(latest.status)) {
          stopPolling()
          setBusy(false)
          if (latest.status === 'completed') {
            setNotice('Generation complete. Use Save WAV as… / Save MP3 as… to pick Desktop, Downloads, or a USB drive.')
            void onRefresh()
          } else if (latest.status === 'failed' || latest.status === 'interrupted') {
            setError(latest.error || 'Generation paused. Click Resume to continue this long file.')
          }
        }
      } catch (e) {
        stopPolling()
        setBusy(false)
        setError(e instanceof Error ? e.message : String(e))
      }
    }
    void tick()
    pollRef.current = window.setInterval(tick, 400)
  }

  async function saveProject() {
    setError(null)
    try {
      if (projectId) {
        await api.updateProject(projectId, {
          text,
          language,
          voice_id: voiceId,
          title: projects.find((p) => p.id === projectId)?.title,
        })
        setNotice('Project saved.')
      } else {
        const created = await api.createProject({
          title: language === 'hi' ? 'Hindi Project' : 'English Project',
          text,
          language,
          voice_id: voiceId,
        })
        setProjectId(created.id)
        setNotice('Project created.')
      }
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function generate() {
    setError(null)
    setNotice(null)
    if (!modelReady) {
      setError('TTS model is not installed. Open Models to install it.')
      return
    }
    if (!voiceId) {
      setError('Select or create a voice first.')
      return
    }
    if (!text.trim()) {
      setError('Enter some text.')
      return
    }
    setBusy(true)
    try {
      let pid = projectId
      if (!pid) {
        const created = await api.createProject({
          title: language === 'hi' ? 'Hindi Project' : 'English Project',
          text,
          language,
          voice_id: voiceId,
        })
        pid = created.id
        setProjectId(pid)
      } else {
        await api.updateProject(pid, { text, language, voice_id: voiceId })
      }

      const { job_id, job: createdJob } = await api.generate({
        text,
        language,
        voice_id: voiceId,
        project_id: pid,
        export_mp3: true,
        clone_mode: cloneMode,
        pronunciation: {
          SUBHAG: language === 'hi' ? 'सुभाग' : 'Soobhag',
          HealthTech: language === 'hi' ? 'हेल्थटेक' : 'Health Tech',
        },
      })
      setJob(createdJob || { id: job_id, status: 'queued', progress: 0, current_chunk: 0, total_chunks: 0 })
      startPolling(job_id)
    } catch (e) {
      setBusy(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function cancel() {
    if (!job?.id) return
    try {
      const updated = await api.cancelJob(job.id)
      setJob(updated)
      stopPolling()
      setBusy(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function resume() {
    if (!job?.id) return
    setError(null)
    setNotice('Resuming from completed chunks — finished pieces are kept.')
    setBusy(true)
    try {
      const { job: next } = await api.resumeJob(job.id)
      const restored = next || ((await api.job(job.id)) as Job)
      setJob(restored)
      startPolling(restored.id)
    } catch (e) {
      setBusy(false)
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div>
      <h1 className="page-title">Text to Speech</h1>
      <p className="page-sub">Generate Hindi or English speech with a local cloned voice. Nothing leaves this Mac.</p>

      {!modelReady && (
        <div className="notice warn">
          TTS model is not installed. Open Settings → Models to install it from a local package.
        </div>
      )}
      {modelReady && modelWarming && !busy && (
        <div className="notice">
          AI model is warming up in the background. Wait until ready for faster first generation.
        </div>
      )}
      {modelReady && modelLoaded && !modelWarming && !busy && (
        <div className="notice" style={{ opacity: 0.85 }}>
          AI model is loaded in memory — generation should start promptly.
        </div>
      )}
      {notice && <div className="notice">{notice}</div>}
      {error && <div className="notice danger">{error}</div>}

      <div className="panel">
        <div className="grid-2">
          <label className="field">
            <span>Voice</span>
            <select value={voiceId} onChange={(e) => setVoiceId(e.target.value)}>
              <option value="">Select Voice</option>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Language</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value as 'hi' | 'en')}>
              <option value="hi">Hindi</option>
              <option value="en">English</option>
            </select>
          </label>
        </div>

        <label className="field" style={{ marginTop: 16 }}>
          <span>Your voice — pick speed or quality</span>
          <select
            value={cloneMode}
            onChange={(e) => setCloneMode(e.target.value as 'fast' | 'quality')}
          >
            <option value="fast">Fast clone — your voice, as quick as this Mac allows</option>
            <option value="quality">Best clone — your voice, slower, closer match</option>
          </select>
        </label>
        <p className="muted" style={{ marginTop: 8, marginBottom: 0 }}>
          Both use the selected cloned voice. Fast skips extra GPU steps. Best runs the full clone
          model. No cloud. 5 minutes of audio in 1–2 minutes is typical of cloud APIs; Fast is the
          closest offline target (often ~2–6 min for a 5 min track after the model is loaded).
        </p>

        <label className="field" style={{ marginTop: 16 }}>
          <span>Text</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste or type your text here..."
            spellCheck={false}
          />
        </label>

        <div className="stats">
          <span>Characters: {stats.chars.toLocaleString()}</span>
          <span>Words: {stats.words.toLocaleString()}</span>
          <span>Estimated audio: ~{stats.mins.toFixed(1)} min</span>
          <span>Est. generate time: ~{stats.genMins < 1 ? `${Math.round(stats.genMins * 60)}s` : `${stats.genMins.toFixed(1)} min`}</span>
        </div>

        {stats.chars > 2500 && (
          <div className="notice" style={{ marginTop: 12 }}>
            Long episode is supported. Fast mode generates many short GPU-safe pieces, then
            stitches one WAV + MP3 (~{stats.mins.toFixed(1)} min). After the model is loaded,
            aim is near realtime (a 5 min track often ~2–6 min). Leave the app running, or
            Resume if it pauses.
          </div>
        )}

        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={generate}>
            {busy ? 'Generating…' : 'Generate Speech'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={saveProject}>
            Save Project
          </button>
          <button type="button" className="btn btn-ghost" disabled={!busy || !job} onClick={cancel}>
            Stop
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy || !job || !['failed', 'interrupted', 'cancelled'].includes(job.status || '')}
            onClick={resume}
          >
            Resume
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              setText('')
              setJob(null)
              setNotice(null)
              setError(null)
              sessionStorage.removeItem(DRAFT_KEY)
            }}
          >
            Clear
          </button>
        </div>

        {job && (
          <>
            {busy && isLoadingStage(job.stage) && (
              <div className="muted" style={{ marginTop: 14, marginBottom: 6 }}>
                Cold start loads ~3 GB of weights into Apple Silicon memory. Later runs reuse the
                loaded model. You can switch tabs — progress keeps running.
              </div>
            )}
            <ProgressBar
              stage={job.stage}
              progress={job.progress || 0}
              currentChunk={job.current_chunk}
              totalChunks={job.total_chunks}
            />
          </>
        )}

        <AudioPlayer
          jobId={job?.id}
          wavPath={job?.output_wav && job.id ? `${getBaseUrl()}/jobs/${job.id}/audio.wav` : null}
          mp3Path={job?.output_mp3 && job.id ? `${getBaseUrl()}/jobs/${job.id}/audio.mp3` : null}
          wavLabel={job?.output_wav}
          mp3Label={job?.output_mp3}
          onMessage={setNotice}
        />
      </div>

      <ImportVoiceHint onImported={onRefresh} />
    </div>
  )
}

function ImportVoiceHint({ onImported }: { onImported: () => Promise<void> }) {
  const [msg, setMsg] = useState<string | null>(null)
  async function pick() {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: 'Audio', extensions: ['wav', 'mp3', 'm4a', 'flac', 'aiff', 'aif'] }],
      })
      if (!selected || Array.isArray(selected)) return
      await api.createVoice({
        name: 'Imported Voice',
        language: 'hi',
        source_audio: selected,
      })
      setMsg('Voice imported and stored locally.')
      await onImported()
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div style={{ marginTop: 18 }} className="muted">
      Need a voice? Go to Voices, or{' '}
      <button type="button" className="btn" onClick={pick}>
        Import Audio
      </button>
      {msg && <div className="notice" style={{ marginTop: 12 }}>{msg}</div>}
    </div>
  )
}
