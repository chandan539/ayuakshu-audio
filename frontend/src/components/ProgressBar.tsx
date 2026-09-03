type Props = {
  stage?: string
  progress: number
  currentChunk?: number
  totalChunks?: number
}

export function ProgressBar({ stage, progress, currentChunk, totalChunks }: Props) {
  const showChunk =
    typeof currentChunk === 'number' &&
    typeof totalChunks === 'number' &&
    totalChunks > 0 &&
    currentChunk > 0

  return (
    <div className="progress-wrap">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <strong>{stage || 'Working…'}</strong>
        <span className="muted">{Math.round(progress)}%</span>
      </div>
      {showChunk && (
        <div className="muted" style={{ marginTop: 6 }}>
          Chunk {currentChunk} / {totalChunks}
        </div>
      )}
      <div className="progress-bar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
      </div>
    </div>
  )
}
