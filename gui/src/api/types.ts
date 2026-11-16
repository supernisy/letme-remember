// letme-remember GUI 数据类型定义（对齐后端 gui_server.py 的 JSON API）

/** 记忆条目（/api/memories、/api/overview 返回的记忆结构） */
export interface Memory {
  id: string
  name: string
  abstract: string
  type: 'semantic' | 'episodic' | 'procedural'
  boost: number
  created: string
  updated: string
  valid_from: string | null
  invalid_at: string | null
  superseded_by: string | null
  author: string
  provenance: string | null
}

/** 健康四维（/api/overview 的 health 字段） */
export interface HealthDimension {
  score: number | null
  [key: string]: unknown
}

/** 总览（/api/overview） */
export interface Overview {
  total: number
  type_count: Record<string, number>
  superseded: number
  has_provenance: number
  has_boost: number
  files: { store: number; archive: number }
  authors: { name: string; n: number }[]
  vector: { indexed?: number; dim?: number; [k: string]: unknown }
  embedding: { enabled: boolean; model: string }
  serve_state: string
  health: Record<string, HealthDimension>
}

/** 系统状态（/api/status） */
export interface Status {
  serve_state: string
  embedding: { enabled: boolean; model: string }
  vector: { indexed?: number; dim?: number; [k: string]: unknown }
  data_dir: string
  files: { store: number; archive: number }
}

/** 记忆列表（/api/memories） */
export interface MemoryList {
  total: number
  items: Memory[]
}

/** 记忆详情（/api/memory/{id}） */
export interface MemoryDetail {
  id: string
  meta: Record<string, string>
  conclusion: string
  reason: string
  access: { count: number; last_at: string }
  path: string
}

/** 健康诊断条目（/api/health） */
export interface HealthIssue {
  id: string
  name: string
  type: string
  abstract: string
  flags: string[]
  access_count: number
  last_accessed: string
  stale_days: number | null
  has_provenance: boolean
}
