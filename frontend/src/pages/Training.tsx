import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Card, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { PlanResponse } from '../types'

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export default function Training() {
  const uid = useApp((s) => s.uid)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const [offlineMode, setOfflineMode] = useState(false)
  useEffect(() => {
    api.plan(uid).then((p) => { api.cachePlan(uid, p); setPlan(p) })
      .catch((e) => {
        // 断网降级：用最近一次加载的计划展示（训练执行页同样降级）
        const cached = api.cachedPlan(uid)
        if ((e as { status?: number }).status === 0 && cached) {
          setPlan(cached); setOfflineMode(true)
        } else {
          setError(e.message)
        }
      })
  }, [uid])

  if (error) {
    return (
      <div className="space-y-3 pt-4">
        <PageHeader title="训练" />
        <ErrorBox message={error} />
        <Link to="/coach" className="btn-ghost block text-center">去 AI 教练页完成建档</Link>
      </div>
    )
  }
  if (!plan) return <Spinner />

  const weekday = WEEKDAYS[new Date().getDay()]
  const deload = plan.content.deload
  const deloadActive = deload && deload.until >= new Date().toISOString().slice(0, 10)

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="训练"
        sub={`${plan.content.template} · 计划 v${plan.version}`} />
      {offlineMode && (
        <p className="rounded-xl bg-amber-950/40 p-2.5 text-xs text-amber-300">
          当前离线：显示最近一次加载的计划；训练记录会暂存本机，恢复网络自动同步。
        </p>
      )}

      {plan.fenced && (
        <div className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
          ⚠️ 计划已隔离，以下内容仅作历史参考；去 AI 教练页处理安全记录并确认重排。
        </div>
      )}
      {deloadActive && (
        <div className="rounded-xl bg-amber-950/40 p-3 text-sm text-amber-300">
          卸载周进行中（至 {deload!.until.slice(5)}）：重量按 {Math.round(deload!.factor * 100)}% 执行。
        </div>
      )}

      <div className="flex gap-2">
        <button className="btn-primary flex-1"
                onClick={() => navigate('/training/edit')}>
          编辑计划
        </button>
        <Link to="/history" className="btn-ghost flex-1 text-center">训练历史</Link>
      </div>

      {plan.content.schedule.map((d) => (
        <Card key={d.day}
              title={<span className={d.day === weekday ? 'text-accent' : ''}>{d.day} · {d.focus}</span>}
              right={<Tag>{d.estimated_minutes ? `约 ${d.estimated_minutes} 分钟` : '—'}</Tag>}>
          <ul className="space-y-2">
            {d.exercises.map((ex, i) => (
              <li key={i} className="text-sm">
                <div className="flex justify-between">
                  <span className={ex.exercise_id ? '' : 'text-neutral-400'}>{ex.name}</span>
                  <span className="text-neutral-300">
                    {ex.sets}×{ex.reps}{ex.weight_kg ? ` · ${ex.weight_kg}kg` : ''}
                  </span>
                </div>
                {(ex.note || ex.why) && (
                  <p className="text-xs text-neutral-500">{ex.note || ex.why}</p>
                )}
              </li>
            ))}
          </ul>
          {plan.fenced ? (
            <p className="mt-3 text-xs text-red-300">
              计划已隔离：旧动作安排暂不能执行（历史与实际活动记录不受影响）。
            </p>
          ) : (
            <button className="btn-ghost mt-3 w-full"
                    onClick={() => navigate(`/workout/${encodeURIComponent(d.day)}`)}>
              开始这天的训练
            </button>
          )}
        </Card>
      ))}

      <Card title="计划备注">
        <ul className="list-disc space-y-1 pl-4 text-xs text-neutral-400">
          {plan.content.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </Card>
    </div>
  )
}
