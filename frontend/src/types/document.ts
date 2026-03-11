// ── 对应 backend/app/models/document.py ──────────────────────────────

export type DocumentSourceType = 'pdf' | 'markdown' | 'text' | 'url'

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed'

// GET /api/v1/kb/documents  文档列表项
export interface DocumentResponse {
  id: string
  title?: string | null
  source_type: DocumentSourceType
  source_url?: string | null
  file_name?: string | null
  chunk_count: number
  embedding_model: string
  status: DocumentStatus
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  error_message?: string | null
}

// GET /api/v1/kb/documents  列表响应
export interface DocumentListResponse {
  items: DocumentResponse[]
  total: number
  page: number
  size: number
}

// POST /api/v1/kb/ingest/url 请求体
export interface DocumentIngestURL {
  url: string
  title?: string
  metadata?: Record<string, unknown>
}

// POST /api/v1/kb/ingest/text 请求体
export interface DocumentIngestText {
  text: string
  title: string
  metadata?: Record<string, unknown>
}

// 摄取响应（file / url / text 共用）
export interface DocumentIngestResponse {
  doc_id: string
  status: DocumentStatus
  chunk_count?: number | null
  message: string
}

// POST /api/v1/kb/search 请求体
export interface SearchRequest {
  query: string
  top_k?: number
  filters?: Record<string, unknown>
}

// 检索结果 chunk
export interface SearchChunk {
  doc_id: string
  chunk_id: string
  content: string
  score: number
  metadata: Record<string, unknown>
}

// POST /api/v1/kb/search 响应
export interface SearchResponse {
  query: string
  results: SearchChunk[]
  total: number
}

// GET /api/v1/kb/stats 响应
export interface KBStats {
  total_documents: number
  vectors_count: number
  qdrant_status: string
}
