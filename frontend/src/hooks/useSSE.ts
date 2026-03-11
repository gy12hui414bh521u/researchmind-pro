import { useEffect, useRef, useCallback } from 'react'
import { createSSEConnection } from '@/api'
import { useAuthStore } from '@/store/authStore'
import { useTaskStore } from '@/store/taskStore'
import type { SSEEventType, SSEEventData } from '@/types'

/**
 * useSSE — 建立 SSE 连接并将事件写入 taskStore
 * @param taskId  要监听的任务 ID（null 时不连接）
 */
export function useSSE(taskId: string | null) {
  const esRef    = useRef<EventSource | null>(null)
  const userId   = useAuthStore((s) => s.userId)
  const { appendEvent, setStreaming } = useTaskStore()

  const disconnect = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setStreaming(false)
  }, [setStreaming])

  useEffect(() => {
    if (!taskId) {
      disconnect()
      return
    }

    // 避免重复连接
    if (esRef.current) disconnect()

    const es = createSSEConnection(taskId, userId)
    esRef.current = es
    setStreaming(true)

    const SSE_EVENTS: SSEEventType[] = [
      'task_started',
      'agent_thought',
      'tool_call',
      'tool_result',
      'hitl_required',
      'task_completed',
      'task_failed',
    ]

    // 为每种事件类型注册监听
    SSE_EVENTS.forEach((eventType) => {
      es.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as SSEEventData
          appendEvent(eventType, data)

          // 终态：断开连接
          if (eventType === 'task_completed' || eventType === 'task_failed') {
            disconnect()
          }
        } catch {
          console.error(`[SSE] 解析 ${eventType} 失败:`, e.data)
        }
      })
    })

    // 连接错误处理
    es.onerror = () => {
      console.warn('[SSE] 连接断开，停止重试')
      disconnect()
    }

    return () => disconnect()
  }, [taskId, userId, appendEvent, setStreaming, disconnect])

  return { disconnect }
}
