import { useQuery } from '@tanstack/react-query'
import { healthApi } from '@/api'
import { FlaskConical, BookOpen, Zap, Activity } from 'lucide-react'
import { useTaskList } from '@/hooks/useTaskQuery'
import { useKBStats } from '@/hooks/useKnowledgeQuery'
import StatusBadge from '@/components/ui/StatusBadge'
import { Skeleton } from '@/components/ui/LoadingSkeleton'
import { formatDistanceToNow } from 'date-fns'
import { zhCN } from 'date-fns/locale'

function StatCard({
  icon: Icon, label, value, sub, accent = 'cyan',
}: {
  icon: React.ElementType
  label: string
  value: string | number
  sub?: string
  accent?: 'cyan' | 'violet' | 'emerald' | 'amber'
}) {
  const colors = {
    cyan:    'text-accent-cyan bg-accent-cyan/10',
    violet:  'text-accent-violet bg-accent-violet/10',
    emerald: 'text-accent-emerald bg-accent-emerald/10',
    amber:   'text-accent-amber bg-accent-amber/10',
  }

  return (
    <div className="card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-text-secondary">{label}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colors[accent]}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <div>
        <p className="text-2xl font-display font-bold text-text-primary">{value}</p>
        {sub && <p className="text-xs text-text-muted mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.basic,
    refetchInterval: 15_000,
  })
  const { data: tasks }  = useTaskList(1, 5)
  const { data: kbStats } = useKBStats()

  const completedCount = tasks?.items.filter(t => t.status === 'completed').length ?? 0
  const runningCount   = tasks?.items.filter(
    t => ['planning','researching','writing','reviewing'].includes(t.status)
  ).length ?? 0

  return (
    <div className="max-w-5xl mx-auto space-y-6 animate-fade-in">
      {/* 页面标题 */}
      <div>
        <h2 className="font-display font-bold text-xl text-text-primary">
          工作台总览
        </h2>
        <p className="text-sm text-text-secondary mt-1">
          监控研究任务进度与知识库状态
        </p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={FlaskConical}
          label="总任务数"
          value={tasks?.total ?? '—'}
          sub={`${runningCount} 个运行中`}
          accent="cyan"
        />
        <StatCard
          icon={Zap}
          label="已完成"
          value={completedCount}
          accent="emerald"
        />
        <StatCard
          icon={BookOpen}
          label="知识库文档"
          value={kbStats?.total_documents ?? '—'}
          sub={`${kbStats?.vectors_count ?? 0} 个向量`}
          accent="violet"
        />
        <StatCard
          icon={Activity}
          label="系统状态"
          value={healthLoading ? '检测中' : (health?.status === 'ok' ? '正常' : '异常')}
          sub={`v${health?.version ?? '—'}`}
          accent="amber"
        />
      </div>

      {/* 最近任务 */}
      <div className="card p-5">
        <h3 className="text-sm font-medium text-text-primary mb-4">最近任务</h3>
        {!tasks ? (
          <div className="space-y-3">
            {[1,2,3].map(i => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : tasks.items.length === 0 ? (
          <p className="text-sm text-text-muted text-center py-8">暂无任务，前往「研究任务」页面创建</p>
        ) : (
          <div className="divide-y divide-bg-border">
            {tasks.items.map((task) => (
              <div key={task.id} className="py-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-text-primary truncate">{task.query}</p>
                  <p className="text-xs text-text-muted mt-0.5">
                    {formatDistanceToNow(new Date(task.created_at), { addSuffix: true, locale: zhCN })}
                  </p>
                </div>
                <StatusBadge status={task.status} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
