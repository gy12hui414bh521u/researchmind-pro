// ── 对应 backend/app/models/task.py ──────────────────────────────────

export type TaskStatus =
  | 'pending'
  | 'planning'
  | 'researching'
  | 'writing'
  | 'reviewing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type ResearchDepth = 'quick' | 'standard' | 'deep'

// POST /api/v1/tasks  请求体
export interface TaskCreate {
  query: string
  depth?: ResearchDepth
  context?: string
}

// GET /api/v1/tasks  列表项
export interface TaskResponse {
  id: string
  status: TaskStatus
  query: string
  depth: ResearchDepth
  created_at: string
  started_at?: string | null
  completed_at?: string | null
}

// GET /api/v1/tasks  列表响应
export interface TaskListResponse {
  items: TaskResponse[]
  total: number
  page: number
  size: number
}

// 研究计划（HiTL 审批对象）
export interface TaskPlan {
  steps: string[]
  estimated_sources: number
  estimated_duration_secs: number
  strategy: string
}

// 研究结果
export interface TaskResult {
  summary: string
  sections: ReportSection[]
  sources: SourceRef[]
  confidence_score: number
}

export interface ReportSection {
  title: string
  content: string
  sources: string[]
}

export interface SourceRef {
  url?: string
  title: string
  chunk_ids: string[]
  relevance: number
}

// Token 成本
export interface CostInfo {
  token_input: number
  token_output: number
  cost_usd: number
}

// GET /api/v1/tasks/{id}  详情
export interface TaskDetailResponse extends TaskResponse {
  plan?: TaskPlan | null
  result?: TaskResult | null
  quality_score?: number | null
  iteration_count: number
  hitl_required: boolean
  cost: CostInfo
  error_message?: string | null
}

// POST /api/v1/tasks/{id}/approve  请求体
export type ApproveAction = 'approve' | 'modify' | 'reject'

export interface TaskApprove {
  action: ApproveAction
  comment?: string
  modifications?: Record<string, unknown>
}

// ── SSE 事件类型 ──────────────────────────────────────────────────────

export type SSEEventType =
  | 'task_started'
  | 'agent_thought'
  | 'tool_call'
  | 'tool_result'
  | 'hitl_required'
  | 'task_completed'
  | 'task_failed'

export interface SSEEvent {
  event: SSEEventType
  data: SSEEventData
}

export interface SSEEventData {
  // task_started
  task_id?: string
  // agent_thought
  thought?: string
  node?: string
  // tool_call
  tool_name?: string
  tool_input?: Record<string, unknown>
  // tool_result
  tool_output?: unknown
  // hitl_required
  plan?: TaskPlan
  // task_completed
  result?: TaskResult
  quality_score?: number
  cost?: CostInfo
  // task_failed
  error?: string
  // 通用
  message?: string
  timestamp?: string
}
