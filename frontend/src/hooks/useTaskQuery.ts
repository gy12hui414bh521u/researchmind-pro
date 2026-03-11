import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { tasksApi } from '@/api'
import type { TaskCreate, TaskApprove, TaskDetailResponse } from '@/types'

export const TASK_KEYS = {
  all:    ['tasks'] as const,
  list:   (page: number, size: number) => ['tasks', 'list', page, size] as const,
  detail: (id: string) => ['tasks', id] as const,
}

export function useTaskList(page = 1, size = 20) {
  return useQuery({
    queryKey: TASK_KEYS.list(page, size),
    queryFn:  () => tasksApi.list(page, size),
  })
}

export function useTaskDetail(taskId: string | null) {
  return useQuery({
    queryKey: TASK_KEYS.detail(taskId ?? ''),
    queryFn:  () => tasksApi.get(taskId!),
    enabled:  !!taskId,
    refetchInterval: (query) => {
      // TanStack Query v5：回调参数是 Query 对象，数据在 query.state.data
      const data = query.state.data as TaskDetailResponse | undefined
      const running = ['pending', 'planning', 'researching', 'writing', 'reviewing']
      return data?.status && running.includes(data.status) ? 3000 : false
    },
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: TaskCreate) => tasksApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASK_KEYS.all })
    },
  })
}

export function useApproveTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: TaskApprove }) =>
      tasksApi.approve(taskId, data),
    onSuccess: (_res, { taskId }) => {
      qc.invalidateQueries({ queryKey: TASK_KEYS.detail(taskId) })
    },
  })
}

export function useCancelTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (taskId: string) => tasksApi.cancel(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TASK_KEYS.all })
    },
  })
}
