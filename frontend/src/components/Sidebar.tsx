type Props = {
  page: string
  onNavigate: (page: string) => void
  offline: boolean
  modelReady: boolean
}

const ITEMS = [
  { id: 'tts', label: 'Text to Speech' },
  { id: 'projects', label: 'Projects' },
  { id: 'voices', label: 'Voices' },
  { id: 'models', label: 'Models' },
  { id: 'settings', label: 'Settings' },
  { id: 'privacy', label: 'Privacy' },
]

export function Sidebar({ page, onNavigate, offline, modelReady }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>AYUAKSHU Audio</strong>
        <span>Local voice cloning & TTS</span>
      </div>

      <nav className="nav">
        <button type="button" className="btn-ghost" onClick={() => onNavigate('tts')} style={{
          background: 'rgba(215,239,231,0.14)',
          marginBottom: 8,
          borderRadius: 10,
          padding: '11px 12px',
          border: 0,
          color: 'inherit',
          textAlign: 'left',
          fontWeight: 700,
        }}>
          New Project
        </button>
        {ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={page === item.id ? 'active' : ''}
            onClick={() => onNavigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="sidebar-foot">
        <div className="offline-pill">
          <i />
          {offline ? 'OFFLINE' : 'Online allowed'}
        </div>
        <div style={{ marginTop: 8 }}>
          {modelReady ? 'TTS model ready' : 'TTS model not installed'}
        </div>
      </div>
    </aside>
  )
}
