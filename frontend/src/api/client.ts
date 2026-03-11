import axios, { type AxiosInstance, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/store/authStore'

// ── Axios 实例 ────────────────────────────────────────────────────────

const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ── 请求拦截器：注入 X-User-Id ────────────────────────────────────────
apiClient.interceptors.request.use(
  (config) => {
    const userId = useAuthStore.getState().userId
    if (userId) {
      config.headers['X-User-Id'] = userId
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ── 响应拦截器：统一错误处理 ──────────────────────────────────────────
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      // 开发阶段不需要重定向，生产环境替换为 JWT 刷新逻辑
      console.warn('[API] 未认证，请检查 X-User-Id 配置')
    }

    if (status === 422) {
      console.error('[API] 请求校验失败:', detail)
    }

    return Promise.reject({
      status,
      message: detail ?? error.message ?? '未知错误',
      raw: error,
    })
  },
)

export default apiClient

// ── SSE 连接工厂 ─────────────────────────────────────────────────────
// 返回原生 EventSource（不走 axios，因为 SSE 需要持久连接）

export function createSSEConnection(
  taskId: string,
  userId: string,
): EventSource {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
  const url = `${baseUrl}/api/v1/tasks/${taskId}/stream`

  // EventSource 不支持自定义 Header，通过 URL 参数传递 userId（开发阶段）
  const fullUrl = `${url}?user_id=${encodeURIComponent(userId)}`
  return new EventSource(fullUrl)
}
