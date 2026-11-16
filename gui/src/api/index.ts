// letme-remember GUI API 层：封装后端 6 个只读 JSON API

import type { MemoryDetail, MemoryList, Overview, Status, HealthIssue } from './types'

const BASE = '' // 同源；dev 模式由 vite proxy 转发 /api

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`请求失败：${res.status} ${res.statusText}（${path}）`)
  }
  return res.json() as Promise<T>
}

export function fetchOverview(): Promise<Overview> {
  return get<Overview>('/api/overview')
}

export function fetchStatus(): Promise<Status> {
  return get<Status>('/api/status')
}

export function fetchMemories(params: {
  q?: string
  type?: string
  sup?: boolean
  limit?: number
  offset?: number
} = {}): Promise<MemoryList> {
  const qs = new URLSearchParams()
  if (params.q) qs.set('q', params.q)
  if (params.type) qs.set('type', params.type)
  if (params.sup) qs.set('sup', '1')
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return get<MemoryList>(`/api/memories${query ? `?${query}` : ''}`)
}

export function fetchMemoryDetail(id: string): Promise<MemoryDetail> {
  return get<MemoryDetail>(`/api/memory/${encodeURIComponent(id)}`)
}

export function fetchHealth(): Promise<{ issues: HealthIssue[] }> {
  return get<{ issues: HealthIssue[] }>('/api/health')
}
