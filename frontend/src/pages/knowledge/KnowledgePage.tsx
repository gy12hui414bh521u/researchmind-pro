import { useState, useRef, useCallback } from 'react'
import {
  BookOpen, Upload, Link, FileText, Trash2, Search,
  CheckCircle2, AlertCircle, Clock, Loader2,
  Database, Layers, Globe, FileType, BarChart3,
  ChevronDown, Plus, ExternalLink
} from 'lucide-react'
import {
  useDocumentList, useKBStats, useIngestFile,
  useIngestUrl, useDeleteDocument, useKBSearch,
} from '@/hooks/useKnowledgeQuery'
import type { DocumentResponse, DocumentStatus, SearchChunk } from '@/types'

// ── 样式常量 ─────────────────────────────────────────────────────────

const STATUS_CFG: Record<DocumentStatus, { label: string; color: string; icon: React.ElementType }> = {
  pending:    { label: '等待中', color: 'text-amber-400',  icon: Clock },
  processing: { label: '处理中', color: 'text-blue-400',   icon: Loader2 },
  completed:  { label: '已就绪', color: 'text-green-400',  icon: CheckCircle2 },
  failed:     { label: '失败',   color: 'text-red-400',    icon: AlertCircle },
}

const SOURCE_CFG = {
  pdf:      { label: 'PDF',      icon: FileType,  color: 'text-red-400' },
  markdown: { label: 'Markdown', icon: FileText,  color: 'text-sky-400' },
  text:     { label: '文本',     icon: FileText,  color: 'text-zinc-400' },
  url:      { label: '网页',     icon: Globe,     color: 'text-emerald-400' },
}

// ── 子组件 ────────────────────────────────────────────────────────────

function StatsBar() {
  const { data: stats, isLoading } = useKBStats()

  const items = [
    { label: '文档总数',   value: stats?.total_documents ?? 0,  icon: Database },
    { label: '向量数量',   value: stats?.vectors_count ?? 0,    icon: Layers },
    { label: 'Qdrant',    value: stats?.qdrant_status ?? '—',   icon: BarChart3 },
  ]

  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map(({ label, value, icon: Icon }) => (
        <div key={label} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <Icon size={13} className="text-zinc-500" />
            <span className="text-xs text-zinc-500">{label}</span>
          </div>
          {isLoading
            ? <div className="h-5 w-12 bg-zinc-800 rounded animate-pulse" />
            : <span className="text-lg font-semibold text-zinc-200">
                {typeof value === 'number' ? value.toLocaleString() : value}
              </span>
          }
        </div>
      ))}
    </div>
  )
}

function DropZone({ onFile }: { onFile: (f: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) onFile(file)
  }, [onFile])

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className={`relative rounded-xl border-2 border-dashed transition-all duration-200 cursor-pointer
        flex flex-col items-center justify-center gap-2 py-8
        ${dragging
          ? 'border-emerald-500/60 bg-emerald-500/5'
          : 'border-zinc-700 hover:border-zinc-600 bg-zinc-900/20'
        }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.md,.markdown,.txt"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f) }}
      />
      <Upload size={24} className={dragging ? 'text-emerald-400' : 'text-zinc-500'} />
      <div className="text-center">
        <p className="text-sm text-zinc-400">拖放文件或点击上传</p>
        <p className="text-xs text-zinc-600 mt-0.5">支持 PDF · Markdown · TXT</p>
      </div>
    </div>
  )
}

function UrlIngestForm() {
  const [url, setUrl]   = useState('')
  const [title, setTitle] = useState('')
  const ingest = useIngestUrl()

  const handleSubmit = () => {
    if (!url.trim()) return
    ingest.mutate(
      { url: url.trim(), title: title.trim() || undefined },
      { onSuccess: () => { setUrl(''); setTitle('') } },
    )
  }

  return (
    <div className="space-y-2">
      <input
        type="url"
        className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2
                   text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none
                   focus:border-zinc-600 transition-colors"
        placeholder="https://example.com/article"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
      />
      <div className="flex gap-2">
        <input
          type="text"
          className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2
                     text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none
                     focus:border-zinc-600 transition-colors"
          placeholder="标题（可选）"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <button
          onClick={handleSubmit}
          disabled={!url.trim() || ingest.isPending}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600/80
                     hover:bg-emerald-500/80 disabled:opacity-40 text-sm text-white
                     font-medium transition-colors"
        >
          {ingest.isPending ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          摄取
        </button>
      </div>
    </div>
  )
}

function DocRow({ doc, onDelete }: { doc: DocumentResponse; onDelete: (id: string) => void }) {
  const statusCfg = STATUS_CFG[doc.status]
  const StatusIcon = statusCfg.icon
  const srcCfg = SOURCE_CFG[doc.source_type] ?? SOURCE_CFG.text
  const SrcIcon = srcCfg.icon

  return (
    <div className="group flex items-center gap-3 px-4 py-3 rounded-lg border border-zinc-800/50
                    bg-zinc-900/20 hover:border-zinc-700 hover:bg-zinc-900/40 transition-all">
      <SrcIcon size={16} className={`shrink-0 ${srcCfg.color}`} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-zinc-200 truncate font-medium">
            {doc.title || doc.file_name || doc.source_url || '未命名'}
          </p>
          {doc.source_url && (
            <a
              href={doc.source_url}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="text-zinc-600 hover:text-zinc-400"
            >
              <ExternalLink size={11} />
            </a>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          <span className={`inline-flex items-center gap-1 text-xs ${statusCfg.color}`}>
            <StatusIcon size={11} className={doc.status === 'processing' ? 'animate-spin' : ''} />
            {statusCfg.label}
          </span>
          <span className="text-xs text-zinc-600">{srcCfg.label}</span>
          {doc.chunk_count > 0 && (
            <span className="text-xs text-zinc-600">{doc.chunk_count} 块</span>
          )}
          <span className="text-xs text-zinc-700">
            {new Date(doc.created_at).toLocaleDateString('zh')}
          </span>
        </div>
        {doc.error_message && (
          <p className="text-xs text-red-400 mt-0.5 truncate">{doc.error_message}</p>
        )}
      </div>

      <button
        onClick={() => onDelete(doc.id)}
        className="opacity-0 group-hover:opacity-100 p-1.5 rounded-md
                   hover:bg-red-500/10 text-zinc-600 hover:text-red-400 transition-all"
        title="删除"
      >
        <Trash2 size={13} />
      </button>
    </div>
  )
}

function SearchPanel() {
  const [query, setQuery]   = useState('')
  const [topK,  setTopK]    = useState(5)
  const search = useKBSearch()

  const handleSearch = () => {
    if (!query.trim()) return
    search.mutate({ query: query.trim(), top_k: topK })
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          type="text"
          className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-2
                     text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none
                     focus:border-zinc-600 transition-colors"
          placeholder="输入语义搜索词..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <select
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-2 text-sm
                     text-zinc-400 focus:outline-none focus:border-zinc-600"
        >
          {[3, 5, 10, 20].map(n => (
            <option key={n} value={n}>Top {n}</option>
          ))}
        </select>
        <button
          onClick={handleSearch}
          disabled={!query.trim() || search.isPending}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600/80
                     hover:bg-sky-500/80 disabled:opacity-40 text-sm text-white
                     font-medium transition-colors"
        >
          {search.isPending ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
          搜索
        </button>
      </div>

      {search.data && (
        <div className="space-y-2">
          <p className="text-xs text-zinc-500">
            找到 {search.data.total} 个相关片段
          </p>
          {search.data.results.map((chunk: SearchChunk) => (
            <div
              key={chunk.chunk_id}
              className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs text-zinc-500 font-mono">
                  {chunk.doc_id.slice(0, 8)}…
                </span>
                <span className="text-xs font-semibold text-sky-400">
                  {(chunk.score * 100).toFixed(1)}%
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed line-clamp-4">
                {chunk.content}
              </p>
            </div>
          ))}
        </div>
      )}

      {search.isError && (
        <div className="text-xs text-red-400 flex items-center gap-1.5">
          <AlertCircle size={12} />
          搜索失败，请检查知识库状态
        </div>
      )}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────

type Tab = 'file' | 'url'

export default function KnowledgePage() {
  const [tab, setTab]         = useState<Tab>('file')
  const [page, setPage]       = useState(1)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [showFilter, setShowFilter]     = useState(false)

  const { data: docList, isLoading } = useDocumentList(page, 20, statusFilter)
  const ingestFile = useIngestFile()
  const deleteDoc  = useDeleteDocument()

  const handleFile = (file: File) => {
    ingestFile.mutate({ file })
  }

  const docs = docList?.items ?? []
  const total = docList?.total ?? 0

  const FILTER_OPTIONS = [
    { value: undefined, label: '全部' },
    { value: 'completed',  label: '已就绪' },
    { value: 'processing', label: '处理中' },
    { value: 'failed',     label: '失败' },
  ]

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
          <BookOpen size={20} className="text-emerald-400" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">知识库</h1>
          <p className="text-xs text-zinc-500">管理文档、摄取内容、语义检索预览</p>
        </div>
      </div>

      {/* 统计条 */}
      <StatsBar />

      <div className="grid grid-cols-5 gap-5">
        {/* 左侧：摄取面板 */}
        <div className="col-span-2 space-y-4">
          {/* Tab 切换 */}
          <div className="flex rounded-lg border border-zinc-800 p-0.5 bg-zinc-900/50 w-fit gap-0.5">
            {([['file', Upload, '上传文件'], ['url', Link, '摄取网页']] as const).map(([id, Icon, label]) => (
              <button
                key={id}
                onClick={() => setTab(id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                  ${tab === id
                    ? 'bg-zinc-700 text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-300'
                  }`}
              >
                <Icon size={12} />
                {label}
              </button>
            ))}
          </div>

          {/* 上传区 */}
          {tab === 'file' && (
            <div className="space-y-3">
              <DropZone onFile={handleFile} />
              {ingestFile.isPending && (
                <div className="flex items-center gap-2 text-xs text-emerald-400">
                  <Loader2 size={12} className="animate-spin" />
                  正在提交摄取任务...
                </div>
              )}
              {ingestFile.data && (
                <div className="flex items-center gap-2 text-xs text-green-400 bg-green-500/5
                                border border-green-500/20 rounded-lg px-3 py-2">
                  <CheckCircle2 size={12} />
                  {ingestFile.data.message}
                </div>
              )}
            </div>
          )}

          {tab === 'url' && (
            <UrlIngestForm />
          )}

          {/* 语义搜索 */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Search size={14} className="text-sky-400" />
              <span className="text-sm font-medium text-zinc-200">语义搜索预览</span>
            </div>
            <SearchPanel />
          </div>
        </div>

        {/* 右侧：文档列表 */}
        <div className="col-span-3 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
              文档列表
              {total > 0 && <span className="ml-2 text-zinc-600 normal-case">（{total} 篇）</span>}
            </span>

            {/* 状态过滤 */}
            <div className="relative">
              <button
                onClick={() => setShowFilter(!showFilter)}
                className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300
                           transition-colors px-2 py-1 rounded hover:bg-zinc-800"
              >
                {FILTER_OPTIONS.find(o => o.value === statusFilter)?.label ?? '全部'}
                <ChevronDown size={11} className={`transition-transform ${showFilter ? 'rotate-180' : ''}`} />
              </button>
              {showFilter && (
                <div className="absolute right-0 top-full mt-1 z-10 rounded-lg border border-zinc-700
                                bg-zinc-800 shadow-xl shadow-black/40 overflow-hidden w-28">
                  {FILTER_OPTIONS.map(opt => (
                    <button
                      key={String(opt.value)}
                      onClick={() => { setStatusFilter(opt.value); setPage(1); setShowFilter(false) }}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-zinc-700 transition-colors
                        ${statusFilter === opt.value ? 'text-emerald-400' : 'text-zinc-300'}`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 列表内容 */}
          {isLoading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="h-16 rounded-lg bg-zinc-900/40 border border-zinc-800 animate-pulse" />
              ))}
            </div>
          ) : docs.length === 0 ? (
            <div className="text-center py-20 text-zinc-600">
              <BookOpen size={32} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">知识库为空</p>
              <p className="text-xs mt-1">上传文档或摄取网页开始构建</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {docs.map((doc) => (
                <DocRow
                  key={doc.id}
                  doc={doc}
                  onDelete={(id) => deleteDoc.mutate(id)}
                />
              ))}
            </div>
          )}

          {/* 分页 */}
          {total > 20 && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage(p => p - 1)}
                className="px-3 py-1 text-xs rounded border border-zinc-700 text-zinc-400
                           hover:border-zinc-600 disabled:opacity-40 transition-colors"
              >
                上一页
              </button>
              <span className="text-xs text-zinc-500">
                {page} / {Math.ceil(total / 20)}
              </span>
              <button
                disabled={page >= Math.ceil(total / 20)}
                onClick={() => setPage(p => p + 1)}
                className="px-3 py-1 text-xs rounded border border-zinc-700 text-zinc-400
                           hover:border-zinc-600 disabled:opacity-40 transition-colors"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}