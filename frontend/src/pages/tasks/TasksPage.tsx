import { useState, useRef, useEffect } from 'react'
import {
  FlaskConical, ChevronDown, Send, X, CheckCircle2,
  AlertCircle, Clock, Loader2, FileText, Zap, Eye,
  ThumbsUp, ThumbsDown, ChevronRight, Activity,
  Search, Cpu, PenLine, ShieldCheck, BarChart3
} from 'lucide-react'
import { useTaskList, useCreateTask, useApproveTask, useCancelTask } from '@/hooks/useTaskQuery'
import { useSSE } from '@/hooks/useSSE'
import { useTaskStore } from '@/store/taskStore'
import type { TaskResponse, SSEEventType, SSEEventData } from '@/types'

// ── 样式常量 ─────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  pending:     { label: '等待中',   color: 'text-amber-400',   icon: Clock },
  planning:    { label: '规划中',   color: 'text-blue-400',    icon: Cpu },
  researching: { label: '研究中',   color: 'text-violet-400',  icon: Search },
  writing:     { label: '撰写中',   color: 'text-emerald-400', icon: PenLine },
  reviewing:   { label: '审核中',   color: 'text-sky-400',     icon: ShieldCheck },
  completed:   { label: '已完成',   color: 'text-green-400',   icon: CheckCircle2 },
  failed:      { label: '失败',     color: 'text-red-400',     icon: AlertCircle },
  cancelled:   { label: '已取消',   color: 'text-zinc-500',    icon: X },
}

const EVENT_CONFIG: Record<SSEEventType, { label: string; color: string; icon: React.ElementType }> = {
  task_started:    { label: '任务启动',   color: 'text-blue-400',    icon: Zap },
  agent_thought:   { label: 'Agent 思考', color: 'text-violet-400',  icon: Cpu },
  tool_call:       { label: '工具调用',   color: 'text-amber-400',   icon: Activity },
  tool_result:     { label: '工具结果',   color: 'text-emerald-400', icon: CheckCircle2 },
  hitl_required:   { label: '需要审批',   color: 'text-orange-400',  icon: Eye },
  task_completed:  { label: '任务完成',   color: 'text-green-400',   icon: CheckCircle2 },
  task_failed:     { label: '任务失败',   color: 'text-red-400',     icon: AlertCircle },
}

const DEPTH_OPTIONS = [
  { value: 'quick' as const, label: '快速', desc: '~5分钟，基础检索' },
  { value: 'deep'  as const, label: '深度', desc: '~30分钟，全面分析' },
]

// ── 子组件 ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${cfg.color}`}>
      <Icon size={12} />
      {cfg.label}
    </span>
  )
}

function EventRow({ event, data, timestamp }: {
  event: SSEEventType
  data: SSEEventData
  timestamp: number
}) {
  const cfg = EVENT_CONFIG[event] ?? { label: event, color: 'text-zinc-400', icon: Activity }
  const Icon = cfg.icon
  const [expanded, setExpanded] = useState(false)

  const summary = typeof data === 'object' && data !== null
    ? (data as Record<string, unknown>).content
      ?? (data as Record<string, unknown>).thought
      ?? (data as Record<string, unknown>).message
      ?? ''
    : ''

  const summaryStr = typeof summary === 'string' ? summary : JSON.stringify(summary)

  return (
    <div
      className="group border-l-2 border-zinc-800 pl-3 py-1.5 hover:border-zinc-600 transition-colors cursor-pointer"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start gap-2">
        <Icon size={13} className={`mt-0.5 shrink-0 ${cfg.color}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>
            <span className="text-xs text-zinc-600">
              {new Date(timestamp).toLocaleTimeString('zh', { hour12: false })}
            </span>
          </div>
          {summaryStr && (
            <p className={`text-xs text-zinc-400 mt-0.5 ${expanded ? '' : 'line-clamp-2'}`}>
              {summaryStr}
            </p>
          )}
          {expanded && (
            <pre className="mt-1 text-xs text-zinc-500 bg-zinc-900/60 rounded p-2 overflow-auto max-h-40">
              {JSON.stringify(data, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

function HiTLPanel({
  taskId,
  onDone,
}: {
  taskId: string
  onDone: () => void
}) {
  const [comment, setComment] = useState('')
  const approve = useApproveTask()

  const handle = (action: 'approve' | 'reject') => {
    approve.mutate(
      { taskId, data: { action, comment } },
      { onSuccess: onDone },
    )
  }

  return (
    <div className="rounded-lg border border-orange-500/30 bg-orange-950/20 p-4 space-y-3">
      <div className="flex items-center gap-2 text-orange-400">
        <Eye size={16} />
        <span className="text-sm font-semibold">需要您的审批</span>
      </div>
      <p className="text-xs text-zinc-400">
        Agent 已生成研究计划，请审阅后选择是否继续执行。
      </p>
      <textarea
        className="w-full text-xs bg-zinc-900 border border-zinc-700 rounded px-3 py-2
                   text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-zinc-500
                   resize-none h-20"
        placeholder="可选：添加修改意见或备注..."
        value={comment}
        onChange={(e) => setComment(e.target.value)}
      />
      <div className="flex gap-2">
        <button
          onClick={() => handle('approve')}
          disabled={approve.isPending}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded
                     bg-green-500/20 hover:bg-green-500/30 border border-green-500/40
                     text-green-400 text-xs font-medium transition-colors disabled:opacity-50"
        >
          <ThumbsUp size={12} />
          批准执行
        </button>
        <button
          onClick={() => handle('reject')}
          disabled={approve.isPending}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded
                     bg-red-500/10 hover:bg-red-500/20 border border-red-500/30
                     text-red-400 text-xs font-medium transition-colors disabled:opacity-50"
        >
          <ThumbsDown size={12} />
          拒绝取消
        </button>
      </div>
    </div>
  )
}

function StreamPanel({ taskId }: { taskId: string }) {
  const { eventLog, isStreaming } = useTaskStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  useSSE(taskId)

  const needsHiTL = eventLog.some((e) => e.event === 'hitl_required')
  const isCompleted = eventLog.some((e) => e.event === 'task_completed')
  const isFailed = eventLog.some((e) => e.event === 'task_failed')

  const completedEntry = eventLog.find((e) => e.event === 'task_completed')
  const report = completedEntry
    ? (completedEntry.data as Record<string, unknown>)?.report as string | undefined
    : undefined

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [eventLog.length])

  return (
    <div className="space-y-3">
      {/* 状态栏 */}
      <div className="flex items-center gap-2 text-xs text-zinc-500">
        {isStreaming && (
          <>
            <Loader2 size={12} className="animate-spin text-violet-400" />
            <span className="text-violet-400">实时推送中...</span>
          </>
        )}
        {isCompleted && (
          <>
            <CheckCircle2 size={12} className="text-green-400" />
            <span className="text-green-400">任务已完成</span>
          </>
        )}
        {isFailed && (
          <>
            <AlertCircle size={12} className="text-red-400" />
            <span className="text-red-400">任务执行失败</span>
          </>
        )}
        <span className="ml-auto">{eventLog.length} 条事件</span>
      </div>

      {/* HiTL 审批 */}
      {needsHiTL && !isCompleted && (
        <HiTLPanel taskId={taskId} onDone={() => {}} />
      )}

      {/* 事件日志 */}
      <div className="space-y-1 max-h-72 overflow-y-auto pr-1 scrollbar-thin">
        {eventLog.length === 0 && (
          <div className="text-center py-8 text-zinc-600 text-xs">
            等待 Agent 响应...
          </div>
        )}
        {eventLog.map((entry) => (
          <EventRow
            key={entry.id}
            event={entry.event}
            data={entry.data}
            timestamp={entry.timestamp}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {/* 报告预览 */}
      {report && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <div className="flex items-center gap-2 mb-3">
            <FileText size={14} className="text-zinc-400" />
            <span className="text-sm font-medium text-zinc-300">研究报告</span>
          </div>
          <div className="prose prose-sm prose-invert max-w-none">
            <pre className="text-xs text-zinc-300 whitespace-pre-wrap font-sans leading-relaxed">
              {report}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}

function TaskCard({
  task,
  isActive,
  onClick,
}: {
  task: TaskResponse
  isActive: boolean
  onClick: () => void
}) {
  return (
    <div
      onClick={onClick}
      className={`group rounded-lg border p-3 cursor-pointer transition-all duration-200
        ${isActive
          ? 'border-violet-500/50 bg-violet-500/5'
          : 'border-zinc-800 hover:border-zinc-700 bg-zinc-900/30'
        }`}
    >
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-zinc-200 font-medium truncate">{task.query}</p>
          <div className="flex items-center gap-3 mt-1">
            <StatusBadge status={task.status} />
            <span className="text-xs text-zinc-600">
              深度 {task.depth} · {new Date(task.created_at).toLocaleDateString('zh')}
            </span>
          </div>
        </div>
        <ChevronRight
          size={14}
          className={`shrink-0 text-zinc-600 mt-1 transition-transform
            ${isActive ? 'rotate-90 text-violet-400' : 'group-hover:translate-x-0.5'}`}
        />
      </div>
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────────────

export default function TasksPage() {
  const [query, setQuery]     = useState('')
  const [depth, setDepth]     = useState<'quick' | 'deep'>('quick')
  const [showDepth, setShowDepth] = useState(false)
  const { setActiveTask, activeTaskId, clearEventLog } = useTaskStore()

  const { data: taskList, isLoading } = useTaskList(1, 30)
  const createTask = useCreateTask()
  const cancelTask = useCancelTask()

  const handleSubmit = () => {
    if (!query.trim() || createTask.isPending) return
    createTask.mutate(
      { query: query.trim(), depth },
      {
        onSuccess: (task) => {
          clearEventLog()
          setActiveTask(task.id)
          setQuery('')
        },
      },
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
  }

  const tasks = taskList?.items ?? []

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* 页头 */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
          <FlaskConical size={20} className="text-violet-400" />
        </div>
        <div>
          <h1 className="text-lg font-semibold text-zinc-100">研究任务</h1>
          <p className="text-xs text-zinc-500">Multi-Agent 智能研究，实时流式推送</p>
        </div>
        {tasks.length > 0 && (
          <div className="ml-auto flex items-center gap-2 text-xs text-zinc-500">
            <BarChart3 size={13} />
            <span>{tasks.filter(t => t.status === 'completed').length} / {tasks.length} 已完成</span>
          </div>
        )}
      </div>

      {/* 创建任务表单 */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
        <div className="relative">
          <textarea
            className="w-full bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 pr-12
                       text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none
                       focus:border-violet-500/50 focus:ring-1 focus:ring-violet-500/20
                       resize-none h-24 transition-colors"
            placeholder="输入研究问题，例如：分析2024年大模型市场竞争格局，重点关注国内外头部厂商的差异化策略..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>

        <div className="flex items-center gap-3">
          {/* 深度选择 */}
          <div className="relative">
            <button
              onClick={() => setShowDepth(!showDepth)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-zinc-700
                         bg-zinc-800/50 text-xs text-zinc-300 hover:border-zinc-600 transition-colors"
            >
              <Zap size={12} className="text-violet-400" />
              {DEPTH_OPTIONS.find(d => d.value === depth)?.label} 模式
              <ChevronDown size={12} className={`transition-transform ${showDepth ? 'rotate-180' : ''}`} />
            </button>
            {showDepth && (
              <div className="absolute top-full left-0 mt-1 z-10 rounded-lg border border-zinc-700
                              bg-zinc-800 shadow-xl shadow-black/40 overflow-hidden w-44">
                {DEPTH_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => { setDepth(opt.value); setShowDepth(false) }}
                    className={`w-full flex flex-col px-3 py-2 text-left hover:bg-zinc-700 transition-colors
                      ${depth === opt.value ? 'bg-violet-500/10' : ''}`}
                  >
                    <span className={`text-xs font-medium ${depth === opt.value ? 'text-violet-400' : 'text-zinc-300'}`}>
                      {opt.label}
                    </span>
                    <span className="text-xs text-zinc-500">{opt.desc}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <span className="text-xs text-zinc-600">⌘↵ 快速提交</span>

          <button
            onClick={handleSubmit}
            disabled={!query.trim() || createTask.isPending}
            className="ml-auto flex items-center gap-2 px-4 py-1.5 rounded-lg
                       bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed
                       text-sm text-white font-medium transition-colors"
          >
            {createTask.isPending
              ? <Loader2 size={14} className="animate-spin" />
              : <Send size={14} />
            }
            {createTask.isPending ? '提交中...' : '开始研究'}
          </button>
        </div>
      </div>

      {/* 主体：任务列表 + 流式面板 */}
      <div className="grid grid-cols-5 gap-4 min-h-[500px]">
        {/* 任务列表 */}
        <div className="col-span-2 space-y-2">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
              历史任务
            </span>
            {isLoading && <Loader2 size={11} className="animate-spin text-zinc-600" />}
          </div>

          {tasks.length === 0 && !isLoading && (
            <div className="text-center py-16 text-zinc-600">
              <FlaskConical size={32} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">还没有任务</p>
              <p className="text-xs mt-1">在上方输入问题开始研究</p>
            </div>
          )}

          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              isActive={activeTaskId === task.id}
              onClick={() => {
                clearEventLog()
                setActiveTask(task.id)
              }}
            />
          ))}
        </div>

        {/* 右侧：流式进度 / 空状态 */}
        <div className="col-span-3">
          {activeTaskId ? (
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/30 p-4 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity size={14} className="text-violet-400" />
                  <span className="text-sm font-medium text-zinc-200">实时进度</span>
                </div>
                <button
                  onClick={() => {
                    cancelTask.mutate(activeTaskId, {
                      onSuccess: () => setActiveTask(null),
                    })
                  }}
                  className="p-1 rounded hover:bg-zinc-800 text-zinc-600 hover:text-zinc-400 transition-colors"
                  title="关闭"
                >
                  <X size={14} />
                </button>
              </div>
              <StreamPanel taskId={activeTaskId} />
            </div>
          ) : (
            <div className="h-full rounded-xl border border-dashed border-zinc-800 flex items-center justify-center">
              <div className="text-center text-zinc-600">
                <Eye size={28} className="mx-auto mb-2 opacity-30" />
                <p className="text-sm">选择任务查看详情</p>
                <p className="text-xs mt-1">或创建新任务开始研究</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}