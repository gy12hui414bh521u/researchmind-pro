import apiClient from './client'
import type {
  TaskCreate, TaskResponse, TaskListResponse,
  TaskDetailResponse, TaskApprove,
} from '@/types'

const BASE = '/api/v1/tasks'

export const tasksApi = {
  // POST /api/v1/tasks
  create: async (data: TaskCreate): Promise<TaskResponse> => {
    const res = await apiClient.post<TaskResponse>(BASE, data)
    return res.data
  },

  // GET /api/v1/tasks
  list: async (page = 1, size = 20): Promise<TaskListResponse> => {
    const res = await apiClient.get<TaskListResponse>(BASE, {
      params: { page, size },
    })
    return res.data
  },

  // GET /api/v1/tasks/{id}
  get: async (taskId: string): Promise<TaskDetailResponse> => {
    const res = await apiClient.get<TaskDetailResponse>(`${BASE}/${taskId}`)
    return res.data
  },

  // POST /api/v1/tasks/{id}/approve
  approve: async (taskId: string, data: TaskApprove): Promise<{ status: string; message: string }> => {
    const res = await apiClient.post(`${BASE}/${taskId}/approve`, data)
    return res.data
  },

  // DELETE /api/v1/tasks/{id}
  cancel: async (taskId: string): Promise<void> => {
    await apiClient.delete(`${BASE}/${taskId}`)
  },
}
