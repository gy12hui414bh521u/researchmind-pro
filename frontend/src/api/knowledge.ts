import apiClient from './client'
import type {
  DocumentListResponse, DocumentIngestURL,
  DocumentIngestText, DocumentIngestResponse,
  SearchRequest, SearchResponse, KBStats,
} from '@/types'

const BASE = '/api/v1/kb'

export const knowledgeApi = {
  // POST /api/v1/kb/ingest/file
  ingestFile: async (file: File, title?: string): Promise<DocumentIngestResponse> => {
    const form = new FormData()
    form.append('file', file)
    if (title) form.append('title', title)
    const res = await apiClient.post<DocumentIngestResponse>(`${BASE}/ingest/file`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  // POST /api/v1/kb/ingest/url
  ingestUrl: async (data: DocumentIngestURL): Promise<DocumentIngestResponse> => {
    const res = await apiClient.post<DocumentIngestResponse>(`${BASE}/ingest/url`, data)
    return res.data
  },

  // POST /api/v1/kb/ingest/text
  ingestText: async (data: DocumentIngestText): Promise<DocumentIngestResponse> => {
    const res = await apiClient.post<DocumentIngestResponse>(`${BASE}/ingest/text`, data)
    return res.data
  },

  // GET /api/v1/kb/documents
  listDocuments: async (page = 1, size = 20, status?: string): Promise<DocumentListResponse> => {
    const res = await apiClient.get<DocumentListResponse>(`${BASE}/documents`, {
      params: { page, size, status },
    })
    return res.data
  },

  // DELETE /api/v1/kb/documents/{id}
  deleteDocument: async (docId: string): Promise<void> => {
    await apiClient.delete(`${BASE}/documents/${docId}`)
  },

  // POST /api/v1/kb/search
  search: async (data: SearchRequest): Promise<SearchResponse> => {
    const res = await apiClient.post<SearchResponse>(`${BASE}/search`, data)
    return res.data
  },

  // GET /api/v1/kb/stats
  stats: async (): Promise<KBStats> => {
    const res = await apiClient.get<KBStats>(`${BASE}/stats`)
    return res.data
  },
}
