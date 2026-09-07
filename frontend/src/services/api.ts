type Json = Record<string, unknown>

let baseUrl = ''

export function setBaseUrl(url: string) {
  baseUrl = url.replace(/\/$/, '')
}

export function getBaseUrl() {
  return baseUrl
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!baseUrl) throw new Error('Backend URL not ready')
  const res = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? JSON.stringify((data as Json).detail)
        : text || res.statusText
    throw new Error(detail)
  }
  return data as T
}

export type Health = {
  status: string
  offline_mode: boolean
  bind: string
  model_ready: boolean
  model_loaded?: boolean
  model_warming?: boolean
  app_data: string
}

export type Voice = {
  id: string
  name: string
  language: string
  engine: string
  reference_audio: string
  metadata?: {
    validation?: {
      duration_sec?: number
      quality?: string
      warnings?: string[]
    }
  }
}

export type Project = {
  id: string
  title: string
  text: string
  voice_id?: string | null
  language: string
  output_wav?: string | null
  output_mp3?: string | null
}

export type ModelInfo = {
  id: string
  name: string
  kind: string
  installed: boolean
  ready_offline: boolean
  path: string
  size_bytes: number
  status: string
  message?: string
  missing_required?: string[]
}

export type SetupStatus = {
  needs_setup: boolean
  setup_completed: boolean
  setup_skipped: boolean
  model_ready: boolean
  model: ModelInfo
}

export type Job = {
  id: string
  status: string
  progress: number
  current_chunk: number
  total_chunks: number
  stage?: string
  error?: string | null
  output_wav?: string | null
  output_mp3?: string | null
  project_id?: string | null
  voice_id?: string | null
  language?: string | null
  text?: string | null
  chunks?: Array<Record<string, unknown>>
}

export type SystemInfo = {
  apple_silicon: boolean
  memory_gb?: number | null
  disk_free_gb?: number | null
  arch: string
  warning?: string | null
  recommended: string
}

export const api = {
  health: () => request<Health>('/health'),
  system: () => request<SystemInfo>('/system'),
  settings: () => request<Record<string, unknown>>('/settings'),
  updateSettings: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  models: () => request<{ models: ModelInfo[] }>('/models'),
  validateModel: (id: string) => request<Record<string, unknown>>(`/models/${id}/validate`),
  validatePackage: (from_local: string) =>
    request<Record<string, unknown>>('/models/validate-package', {
      method: 'POST',
      body: JSON.stringify({ model_id: 'chatterbox', from_local }),
    }),
  installModel: (from_local: string) =>
    request<{
      ok: boolean
      message: string
      model: ModelInfo
      install_path?: string
    }>('/models/install', {
      method: 'POST',
      body: JSON.stringify({ model_id: 'chatterbox', from_local }),
    }),
  setupStatus: () => request<SetupStatus>('/setup/status'),
  setupSkip: () => request<SetupStatus>('/setup/skip', { method: 'POST' }),
  setupComplete: () => request<SetupStatus>('/setup/complete', { method: 'POST' }),
  voices: () => request<{ voices: Voice[] }>('/voices'),
  createVoice: (body: {
    name: string
    language: string
    source_audio: string
    engine?: string
  }) =>
    request<Voice>('/voices', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  uploadVoice: async (args: {
    name: string
    language: string
    blob: Blob
    filename?: string
    engine?: string
  }) => {
    if (!baseUrl) throw new Error('Backend URL not ready')
    const form = new FormData()
    form.append('name', args.name)
    form.append('language', args.language)
    form.append('engine', args.engine || 'chatterbox')
    form.append('file', args.blob, args.filename || 'recording.wav')
    const res = await fetch(`${baseUrl}/voices/upload`, { method: 'POST', body: form })
    const text = await res.text()
    let data: unknown = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }
    if (!res.ok) {
      const detail =
        typeof data === 'object' && data && 'detail' in data
          ? JSON.stringify((data as Json).detail)
          : text || res.statusText
      throw new Error(detail)
    }
    return data as Voice
  },
  deleteVoice: (id: string) =>
    request<{ deleted: boolean }>(`/voices/${id}`, { method: 'DELETE' }),
  transcribe: (body: { audio_path: string; language?: string }) =>
    request<{ text: string; language?: string; segments?: unknown[] }>('/transcribe', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  transcribeUpload: async (args: { blob: Blob; language?: string; filename?: string }) => {
    if (!baseUrl) throw new Error('Backend URL not ready')
    const form = new FormData()
    if (args.language) form.append('language', args.language)
    form.append('file', args.blob, args.filename || 'audio.wav')
    const res = await fetch(`${baseUrl}/transcribe/upload`, { method: 'POST', body: form })
    const text = await res.text()
    let data: unknown = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = text
    }
    if (!res.ok) {
      const detail =
        typeof data === 'object' && data && 'detail' in data
          ? JSON.stringify((data as Json).detail)
          : text || res.statusText
      throw new Error(detail)
    }
    return data as { text: string; language?: string }
  },
  projects: () => request<{ projects: Project[] }>('/projects'),
  createProject: (body: Partial<Project> & { title: string }) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateProject: (id: string, body: Partial<Project>) =>
    request<Project>(`/projects/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteProject: (id: string) =>
    request<{ deleted: boolean }>(`/projects/${id}`, { method: 'DELETE' }),
  generate: (body: {
    text: string
    language: string
    voice_id: string
    project_id?: string
    max_chars?: number
    pronunciation?: Record<string, string>
    export_mp3?: boolean
    clone_mode?: 'fast' | 'quality'
  }) =>
    request<{ job_id: string; job: Job }>('/generate', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  activeJob: () => request<{ job: Job | null }>('/jobs/active'),
  cancelJob: (id: string) =>
    request<Job>(`/jobs/${id}/cancel`, { method: 'POST' }),
  resumeJob: (id: string) =>
    request<{ job_id: string; job: Job }>(`/jobs/${id}/resume`, { method: 'POST' }),
  exportJob: (id: string, body: { format: 'wav' | 'mp3' | 'both'; destination: string; reveal?: boolean }) =>
    request<{
      ok: boolean
      copied: Array<{ format: string; path: string }>
      folder: string
      message: string
    }>(`/jobs/${id}/export`, {
      method: 'POST',
      body: JSON.stringify({ reveal: true, ...body }),
    }),
  revealJob: (id: string, format: 'wav' | 'mp3' = 'wav') =>
    request<{ ok: boolean; path: string; folder: string }>(
      `/jobs/${id}/reveal?format=${format}`,
      { method: 'POST' },
    ),
  clearTemp: () =>
    request<{ removed: number }>('/storage/clear-temporary', { method: 'POST' }),
}
