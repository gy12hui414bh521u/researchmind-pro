// ── 对应 backend/app/api/health.py ───────────────────────────────────

export interface HealthBasic {
  status: 'ok' | 'error'
  version: string
}

export interface HealthDetail {
  status: 'ok' | 'degraded' | 'error'
  components: {
    postgres?: string
    qdrant?: string
    qdrant_vectors?: number
    redis?: string
    llm_providers?: string[]
    embedding?: string
    [key: string]: unknown
  }
}
