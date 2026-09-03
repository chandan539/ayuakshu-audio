type Props = {
  wavPath?: string | null
  mp3Path?: string | null
  wavLabel?: string | null
  mp3Label?: string | null
}

export function AudioPlayer({ wavPath, mp3Path, wavLabel, mp3Label }: Props) {
  if (!wavPath && !mp3Path) return null
  return (
    <div className="audio-box panel" style={{ padding: 16, marginTop: 16 }}>
      <strong>Generated audio</strong>
      {wavPath && (
        <div>
          <div className="muted">WAV {wavLabel ? `· ${wavLabel}` : ''}</div>
          <audio controls src={wavPath} />
        </div>
      )}
      {mp3Path && (
        <div>
          <div className="muted">MP3 {mp3Label ? `· ${mp3Label}` : ''}</div>
          <audio controls src={mp3Path} />
        </div>
      )}
      <div className="btn-row" style={{ marginTop: 4 }}>
        {wavPath && (
          <a className="btn" href={wavPath} download="offlinevoice.wav">
            Export WAV
          </a>
        )}
        {mp3Path && (
          <a className="btn" href={mp3Path} download="offlinevoice.mp3">
            Export MP3
          </a>
        )}
      </div>
    </div>
  )
}
