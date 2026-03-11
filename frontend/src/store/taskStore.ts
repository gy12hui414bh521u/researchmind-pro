import { create } from 'zustand'
import type { SSEEventData, SSEEventType, TaskDetailResponse } from '@/types'

export interface SSELogEntry {
  id: string
  event: SSEEventType
  data: SSEEventData
  timestamp: number
}

interface TaskStreamState {
  // 当前正在流式查看的任务 ID
  activeTaskId: string | null
  // 该任务的 SSE 事件日志（实时追加）
  eventLog: SSELogEntry[]
  // SSE 连接状态
  isStreaming: boolean
  // 任务详情缓存（流完成后更新）
  taskDetail: TaskDetailResponse | null

  // Actions
  setActiveTask: (taskId: string | null) => void
  appendEvent: (event: SSEEventType, data: SSEEventData) => void
  clearEventLog: () => void
  setStreaming: (v: boolean) => void
  setTaskDetail: (detail: TaskDetailResponse | null) => void
}

export const useTaskStore = create<TaskStreamState>((set) => ({
  activeTaskId: null,
  eventLog: [],
  isStreaming: false,
  taskDetail: null,

  setActiveTask: (taskId) =>
    set({ activeTaskId: taskId, eventLog: [], isStreaming: false, taskDetail: null }),

  appendEvent: (event, data) =>
    set((state) => ({
      eventLog: [
        ...state.eventLog,
        {
          id:        `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          event,
          data,
          timestamp: Date.now(),
        },
      ],
    })),

  clearEventLog: () => set({ eventLog: [] }),
  setStreaming:  (v) => set({ isStreaming: v }),
  setTaskDetail: (detail) => set({ taskDetail: detail }),
}))
