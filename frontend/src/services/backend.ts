import { invoke } from '@tauri-apps/api/core'

export type BackendInfo = {
  base_url: string
  ready: boolean
  offline_mode: boolean
}

const isTauri = () =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

export async function resolveBackendUrl(timeoutMs = 90000): Promise<string> {
  const envUrl = import.meta.env.VITE_BACKEND_URL as string | undefined
  if (envUrl) return envUrl.replace(/\/$/, '')

  if (!isTauri()) {
    // Browser-only fallback for vite-only debugging.
    return 'http://127.0.0.1:8765'
  }

  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    try {
      const info = await invoke<BackendInfo>('get_backend_info')
      if (info.ready && info.base_url) return info.base_url.replace(/\/$/, '')
    } catch {
      // keep polling
    }
    await new Promise((r) => setTimeout(r, 300))
  }
  throw new Error('Timed out waiting for local backend')
}
