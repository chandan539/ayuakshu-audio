import { api, type Project } from '../services/api'

type Props = {
  projects: Project[]
  onRefresh: () => Promise<void>
  onOpen: (project: Project) => void
}

export function ProjectsPage({ projects, onRefresh, onOpen }: Props) {
  async function create() {
    await api.createProject({ title: 'Untitled Project', language: 'hi', text: '' })
    await onRefresh()
  }

  async function remove(id: string) {
    await api.deleteProject(id)
    await onRefresh()
  }

  return (
    <div>
      <h1 className="page-title">Projects</h1>
      <p className="page-sub">Each project stores text, voice, language, and generated file paths locally.</p>
      <div className="btn-row" style={{ marginTop: 0, marginBottom: 16 }}>
        <button type="button" className="btn btn-primary" onClick={create}>
          New Project
        </button>
      </div>
      <div className="list">
        {projects.length === 0 && <div className="muted">No projects yet.</div>}
        {projects.map((p) => (
          <div className="list-item" key={p.id}>
            <div>
              <strong>{p.title}</strong>
              <div className="muted">
                {p.language.toUpperCase()} · {(p.text || '').slice(0, 80) || 'Empty'}
              </div>
            </div>
            <div className="btn-row" style={{ marginTop: 0 }}>
              <button type="button" className="btn btn-primary" onClick={() => onOpen(p)}>
                Open
              </button>
              <button type="button" className="btn" onClick={() => remove(p.id)}>
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
