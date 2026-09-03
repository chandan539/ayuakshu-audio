import { useCallback, useEffect, useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { SetupWizard } from './components/SetupWizard'
import { TtsPage } from './pages/TtsPage'
import { VoicesPage } from './pages/VoicesPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ModelsPage } from './pages/ModelsPage'
import { SettingsPage } from './pages/SettingsPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { api, setBaseUrl, type Project, type Voice } from './services/api'
import { resolveBackendUrl } from './services/backend'
import './styles/global.css'

export default function App() {
  const [page, setPage] = useState('tts')
  const [bootError, setBootError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const [offline, setOffline] = useState(true)
  const [modelReady, setModelReady] = useState(false)
  const [needsSetup, setNeedsSetup] = useState(false)
  const [voices, setVoices] = useState<Voice[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [activeProject, setActiveProject] = useState<Project | null>(null)

  const refresh = useCallback(async () => {
    const [health, voiceRes, projectRes, setup] = await Promise.all([
      api.health(),
      api.voices(),
      api.projects(),
      api.setupStatus(),
    ])
    setOffline(Boolean(health.offline_mode))
    setModelReady(Boolean(health.model_ready))
    setNeedsSetup(Boolean(setup.needs_setup))
    setVoices(voiceRes.voices)
    setProjects(projectRes.projects)
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const url = await resolveBackendUrl()
        if (cancelled) return
        setBaseUrl(url)
        await refresh()
        if (!cancelled) setReady(true)
      } catch (e) {
        if (!cancelled) setBootError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [refresh])

  function openProject(project: Project) {
    setActiveProject(project)
    setPage('tts')
  }

  if (bootError) {
    return (
      <div className="main">
        <div className="notice danger">
          <strong>Could not start AYUAKSHU Audio backend.</strong>
          <div>{bootError}</div>
          <p className="muted">
            Ensure `backend/.venv` exists. Model weights can be installed from Models after launch.
          </p>
        </div>
      </div>
    )
  }

  if (!ready) {
    return (
      <div className="main">
        <h1 className="page-title">AYUAKSHU Audio</h1>
        <p className="page-sub">Starting local backend…</p>
        <div className="progress-wrap">
          <strong>Loading AI runtime on this Mac</strong>
          <div className="progress-bar"><span style={{ width: '35%' }} /></div>
        </div>
      </div>
    )
  }

  if (needsSetup) {
    return (
      <SetupWizard
        onCompleted={async () => {
          await refresh()
          setNeedsSetup(false)
          setPage('tts')
        }}
        onSkip={async () => {
          await api.setupSkip()
          await refresh()
          setNeedsSetup(false)
          setPage('models')
        }}
      />
    )
  }

  return (
    <div className="app-shell">
      <Sidebar
        page={page}
        onNavigate={setPage}
        offline={offline}
        modelReady={modelReady}
      />
      <main className="main">
        {!modelReady && page === 'tts' && (
          <div className="notice warn">
            Application ready. TTS model not installed. Go to Models to install it from a local package.
          </div>
        )}
        {/* Keep pages mounted so drafts, progress, and players survive tab switches. */}
        <div className="page-pane" hidden={page !== 'tts'}>
          <TtsPage
            voices={voices}
            projects={projects}
            modelReady={modelReady}
            onRefresh={refresh}
            initialProject={activeProject}
          />
        </div>
        <div className="page-pane" hidden={page !== 'voices'}>
          <VoicesPage voices={voices} onRefresh={refresh} />
        </div>
        <div className="page-pane" hidden={page !== 'projects'}>
          <ProjectsPage projects={projects} onRefresh={refresh} onOpen={openProject} />
        </div>
        <div className="page-pane" hidden={page !== 'models'}>
          <ModelsPage modelReady={modelReady} onRefresh={refresh} />
        </div>
        <div className="page-pane" hidden={page !== 'settings'}>
          <SettingsPage />
        </div>
        <div className="page-pane" hidden={page !== 'privacy'}>
          <PrivacyPage />
        </div>
      </main>
    </div>
  )
}
