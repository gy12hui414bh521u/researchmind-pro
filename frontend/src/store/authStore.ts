import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  // 开发阶段使用 X-User-Id 头，生产环境替换为 JWT
  userId: string
  isAuthDisabled: boolean   // 对应后端 AUTH_DISABLED=true

  // Actions
  setUserId: (id: string) => void
  reset: () => void
}

const DEV_USER_ID = '00000000-0000-0000-0000-000000000001'

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      userId: DEV_USER_ID,
      isAuthDisabled: true,

      setUserId: (id) => set({ userId: id }),
      reset: () => set({ userId: DEV_USER_ID, isAuthDisabled: true }),
    }),
    {
      name: 'researchmind-auth',
    },
  ),
)
