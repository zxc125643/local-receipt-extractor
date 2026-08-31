import type { Asset, PosterPage, Project } from '../types'
import { normalizeLegacyDraft } from '../editor/template'

interface DraftSummary {
  id: number
  project_name: string
  page_count: number
  asset_count: number
  updated_at: string
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const error = await response.json() as { error?: string }
      if (error.error) message = error.error
    } catch {
      // Keep the HTTP fallback message.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export async function uploadAsset(file: Blob, filename: string): Promise<Asset> {
  return request<Asset>('/api/assets', {
    method: 'POST',
    headers: {
      'Content-Type': file.type || 'image/jpeg',
      'X-Filename': encodeURIComponent(filename),
    },
    body: file,
  })
}

function toPayload(project: Project) {
  return {
    id: project.id,
    version: 2,
    project_name: project.projectName,
    project_description: project.description,
    active_page_id: project.activePageId,
    asset_count: project.assets.length,
    page_count: project.pages.length,
    assets: project.assets,
    pages: project.pages,
  }
}

export async function saveDraft(project: Project): Promise<{ id: number; project_name: string; updated_at: string }> {
  return request('/api/drafts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(toPayload(project)),
  })
}

export async function listDrafts(): Promise<DraftSummary[]> {
  const data = await request<{ drafts: DraftSummary[] }>('/api/drafts')
  return data.drafts || []
}

export async function loadDraft(id: number): Promise<Project> {
  const data = await request<Record<string, unknown>>(`/api/drafts/${id}`)
  return normalizeLegacyDraft(data)
}

export async function deleteDraft(id: number): Promise<void> {
  await request(`/api/drafts/${id}`, { method: 'DELETE' })
}

export async function renderPage(project: Project, page: PosterPage): Promise<Blob> {
  const response = await fetch('/api/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projectName: project.projectName, page }),
  })
  if (!response.ok) {
    let message = `原图渲染失败（${response.status}）`
    try {
      const error = await response.json() as { error?: string }
      if (error.error) message = error.error
    } catch {
      // Keep the HTTP fallback message.
    }
    throw new Error(message)
  }
  return response.blob()
}

export async function migrateDataUrlAsset(asset: Asset): Promise<Asset> {
  if (!asset.src.startsWith('data:')) return asset
  const response = await fetch(asset.src)
  const blob = await response.blob()
  const migrated = await uploadAsset(blob, asset.name)
  return { ...migrated, originalSrc: migrated.src }
}
