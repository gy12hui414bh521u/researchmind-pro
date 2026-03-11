import { useLocation } from 'react-router-dom'
import { Bell, CircleUser } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

const ROUTE_TITLES: Record<string, string> = {
  '/dashboard': '总览',
  '/tasks':     '研究任务',
  '/knowledge': '知识库',
  '/settings':  '设置',
}

export default function Header() {
  const { pathname } = useLocation()
  const userId = useAuthStore((s) => s.userId)

  // 匹配路径
  const title = Object.entries(ROUTE_TITLES).find(([key]) =>
    pathname.startsWith(key),
  )?.[1] ?? '页面'

  return (
    <header className="h-14 shrink-0 flex items-center justify-between
                        px-6 border-b border-bg-border bg-bg-surface/80 backdrop-blur-sm">
      {/* 左侧标题 */}
      <div>
        <h1 className="font-display font-semibold text-base text-text-primary">
          {title}
        </h1>
      </div>

      {/* 右侧操作区 */}
      <div className="flex items-center gap-2">
        {/* 通知按钮（占位） */}
        <button className="btn-ghost p-2 rounded-lg">
          <Bell className="w-4 h-4" />
        </button>

        {/* 用户信息 */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg
                        bg-bg-elevated border border-bg-border">
          <CircleUser className="w-4 h-4 text-text-secondary" />
          <span className="text-xs font-mono text-text-secondary truncate max-w-32">
            {userId.slice(0, 8)}…
          </span>
        </div>
      </div>
    </header>
  )
}
