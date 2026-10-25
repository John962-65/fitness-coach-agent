import { useState } from 'react'
import { ChevronDown, ListChecks } from 'lucide-react'
import { TASK_STATUS } from '../../lib/experts'
import { ExpertTask } from '../../types'

const TONE: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-700',
  running: 'bg-accent-soft text-accent-deep',
  ready: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-red-50 text-red-600',
  cancelled: 'bg-ink/5 text-faint',
}

/** 专家任务状态：一行摘要 + 可展开执行日志（含失败原因/重试轨迹） */
export default function ExpertTaskStatus({ task, defaultOpen = false }:
  { task: ExpertTask; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-xl border border-line bg-surface/60">
      <button type="button" className="flex w-full items-center gap-2 p-2.5 text-left text-xs"
              onClick={() => setOpen(!open)}>
        <ListChecks size={14} className="shrink-0 text-muted" />
        <span className="min-w-0 flex-1 truncate">
          {TASK_STATUS[task.task_type] ?? task.task_type}
          <span className="ml-1 text-faint">（{task.trigger_source}）</span>
          {task.error && <span className="ml-1 text-red-600">· {task.error}</span>}
        </span>
        {task.retry_count > 0 && (
          <span className="shrink-0 text-faint">重试 {task.retry_count}</span>
        )}
        <span className={`tag shrink-0 ${TONE[task.status] ?? ''}`}>
          {TASK_STATUS[task.status] ?? task.status}
        </span>
        <ChevronDown size={14} className={`shrink-0 text-muted transition-transform
                                            ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <ul className="space-y-1 border-t border-line px-3 py-2 text-2xs leading-relaxed text-muted">
          {(task.events ?? []).map((e, i) => (
            <li key={i}>[{e.at.slice(5, 16)}] {e.event}{e.detail ? `：${e.detail}` : ''}</li>
          ))}
          <li className="text-faint">任务 {task.id.slice(0, 12)}…
            {task.insight_id ? ` · 产出 ${task.insight_id.slice(0, 12)}…` : ''}</li>
        </ul>
      )}
    </div>
  )
}
