import { useEffect, useState } from 'react'
import { api, type Voice } from '../services/api'

type Preset = { id: string; label: string; prompt: string; stability: number; similarity: number }

type Props = {
  voices: Voice[]
  onCreated: () => Promise<void>
  onClose: () => void
}

export function VoiceDesign({ voices, onCreated, onClose }: Props) {
  const [presets, setPresets] = useState<Preset[]>([])
  const [prompt, setPrompt] = useState('')
  const [presetId, setPresetId] = useState<string | null>(null)
  const [baseId, setBaseId] = useState(voices[0]?.id || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.voiceDesignPresets().then((r) => setPresets(r.presets)).catch(() => undefined)
  }, [])

  async function generate() {
    setError(null)
    if (!baseId) {
      setError('Import or record a voice first. Design uses that recording.')
      return
    }
    if (!prompt.trim() && !presetId) {
      setError('Describe the voice or pick a preset.')
      return
    }
    setBusy(true)
    try {
      await api.designVoice({
        base_voice_id: baseId,
        prompt,
        preset_id: presetId || undefined,
      })
      await onCreated()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-labelledby="voice-design-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="voice-design-title">Voice Design</h2>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="muted">
          Describe how the voice should perform. This stays on this Mac and uses a cloned recording
          you already have. It does not invent a new person from text alone.
        </p>
        <label className="field">
          <span>Based on</span>
          <select value={baseId} onChange={(e) => setBaseId(e.target.value)}>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ marginTop: 14 }}>
          <span>Prompt</span>
          <textarea
            className="design-prompt"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value)
              setPresetId(null)
            }}
            placeholder="A calm Hindi narrator, steady pace, clear and close to the original recording."
          />
        </label>
        <div className="chip-row">
          {presets.map((p) => (
            <button
              key={p.id}
              type="button"
              className={presetId === p.id ? 'chip chip-on' : 'chip'}
              onClick={() => {
                setPresetId(p.id)
                setPrompt(p.prompt)
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
        {error && <div className="notice danger">{error}</div>}
        <div className="btn-row">
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void generate()}>
            {busy ? 'Saving…' : 'Generate voice'}
          </button>
        </div>
      </div>
    </div>
  )
}
