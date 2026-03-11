import { clsx } from 'clsx'
import type { TaskStatus } from '@/types'
import type { DocumentStatus } from '@/types'

type Status = TaskStatus | DocumentStatus

const STATUS_CONFIG: Record<Status, { label: string; cls: string; dot: string }> = {
  // Task statuses
  pending:     { label: '等待中',  cls: 'bg-text-muted/10 text-text-muted',         dot: 'bg-text-muted' },
  planning:    { label: '规划中',  cls: 'bg-accent-violet/10 text-accent-violet',    dot: 'bg-accent-violet animate-pulse' },
  researching: { label: '研究中',  cls: 'bg-accent-cyan/10 text-accent-cyan',        dot: 'bg-accent-cyan animate-pulse' },
  writing:     { label: '撰写中',  cls: 'bg-accent-amber/10 text-accent-amber',      dot: 'bg-accent-amber animate-pulse' },
  reviewing:   { label: '审查中',  cls: 'bg-accent-violet/10 text-accent-violet',    dot: 'bg-accent-violet animate-pulse' },
  completed:   { label: '已完成',  cls: 'bg-accent-emerald/10 text-accent-emerald',  dot: 'bg-accent-emerald' },
  failed:      { label: '失败',    cls: 'bg-accent-rose/10 text-accent-rose',        dot: 'bg-accent-rose' },
  cancelled:   { label: '已取消',  cls: 'bg-text-muted/10 text-text-muted',         dot: 'bg-text-muted' },
  // Document statuses
  processing:  { label: '处理中',  cls: 'bg-accent-cyan/10 text-accent-cyan',        dot: 'bg-accent-cyan animate-pulse' },
}

interface Props {
  status: Status
  className?: string
}

export default function StatusBadge({ status, className }: Props) {
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending

  return (
    <span className={clsx('badge', cfg.cls, className)}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', cfg.dot)} />
      {cfg.label}
    </span>
  )
}
