import apiClient from './client'
import type { HealthBasic, HealthDetail } from '@/types'

export const healthApi = {
  basic: async (): Promise<HealthBasic> => {
    const res = await apiClient.get<HealthBasic>('/api/v1/health')
    return res.data
  },

  detail: async (): Promise<HealthDetail> => {
    const res = await apiClient.get<HealthDetail>('/api/v1/health/detail')
    return res.data
  },
}
