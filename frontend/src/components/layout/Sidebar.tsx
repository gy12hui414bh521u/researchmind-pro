import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FlaskConical,
  BookOpen,
  Settings,
  Brain,
  Zap,
} from 'lucide-react'
import { clsx } from 'clsx'

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: '总览' },
  { to: '/tasks',     icon: FlaskConical,    label: '研究任务' },
  { to: '/knowledge', icon: BookOpen,        label: '知识库' },
]

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 flex flex-col border-r border-bg-border bg-bg-surface">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-bg-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-cyan to-accent-violet
                          flex items-center justify-center shadow-glow-cyan">
            <Brain className="w-4 h-4 text-bg-base" />
          </div>
          <div>
            <p className="font-display font-700 text-sm text-text-primary leading-tight">
              ResearchMind
            </p>
            <p className="text-xs text-accent-cyan font-mono leading-tight">Pro</p>
          </div>
        </div>
      </div>

      {/* 导航 */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="px-3 mb-2 text-xs font-medium text-text-muted uppercase tracking-wider">
          工作区
        </p>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}>
            {({ isActive }) => (
              <span className={clsx('nav-item', isActive && 'active')}>
                <Icon className="w-4 h-4 shrink-0" />
                <span className="text-sm">{label}</span>
                {isActive && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-accent-cyan" />
                )}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* 底部：状态指示 */}
      <div className="px-5 py-4 border-t border-bg-border">
        <div className="flex items-center gap-2 text-xs text-text-muted">
          <Zap className="w-3 h-3 text-accent-emerald" />
          <span>后端连接中</span>
          <span className="ml-auto font-mono text-text-muted/60">v2.0</span>
        </div>

        <NavLink to="/settings" className="nav-item mt-2 text-xs">
          <Settings className="w-3.5 h-3.5" />
          <span>设置</span>
        </NavLink>
      </div>
    </aside>
  )
}
