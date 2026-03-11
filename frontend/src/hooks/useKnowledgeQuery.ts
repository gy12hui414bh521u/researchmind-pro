import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { knowledgeApi } from '@/api'
import type { DocumentIngestURL, DocumentIngestText, SearchRequest } from '@/types'

export const KB_KEYS = {
  all:      ['kb'] as const,
  docs:     (page: number, size: number, status?: string) =>
              ['kb', 'docs', page, size, status] as const,
  stats:    ['kb', 'stats'] as const,
}

export function useDocumentList(page = 1, size = 20, status?: string) {
  return useQuery({
    queryKey: KB_KEYS.docs(page, size, status),
    queryFn:  () => knowledgeApi.listDocuments(page, size, status),
  })
}

export function useKBStats() {
  return useQuery({
    queryKey: KB_KEYS.stats,
    queryFn:  () => knowledgeApi.stats(),
    refetchInterval: 30_000,
  })
}

export function useIngestFile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, title }: { file: File; title?: string }) =>
      knowledgeApi.ingestFile(file, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEYS.all }),
  })
}

export function useIngestUrl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: DocumentIngestURL) => knowledgeApi.ingestUrl(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEYS.all }),
  })
}

export function useIngestText() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: DocumentIngestText) => knowledgeApi.ingestText(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEYS.all }),
  })
}

export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (docId: string) => knowledgeApi.deleteDocument(docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: KB_KEYS.all }),
  })
}

export function useKBSearch() {
  return useMutation({
    mutationFn: (data: SearchRequest) => knowledgeApi.search(data),
  })
}
