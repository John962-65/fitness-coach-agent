import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Card, Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { PlanResponse, TodayBrief } from '../types'

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export default function Today() {
  const uid = useApp((s) => s.uid)
  const session = useApp((s) => s.session)
  const offlineCount = useApp((s) => s.offlineCount)
  const [brief, setBrief] = useState<TodayBrief | null>(null)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([api.today(uid), api.plan(uid).catch(() => null)])
      .then(([b, p]) => { setBrief(b); setPlan(p) })
      .catch((e) => setError(e.message))
  }, [uid])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!brief) return <Spinner />

  const weekday = WEEKDAYS[new Date().getDay()]
  const todayPlan = plan?.content.schedule.find((d) => d.day === weekday)

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="今日"
        sub={`${new Date().toLocaleDateString('zh-CN')} · ${weekday} · 目标 ${(brief.plan_days_per_week ?? 0) || '—'} 练/周`} />

      {offlineCount > 0 && (
        <div className="rounded-xl bg-amber-950/50 p-3 text-sm text-amber-300">
          有 {offlineCount} 条离线训练记录待同步，恢复网络后自动补交。
        </div>
      )}

      {(brief.plan_fenced || !brief.medical.allows_prescription) && (
        <div className="rounded-xl border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
          {brief.plan_fenced
            ? '⚠️ 计划已隔离（伤病/安全记录未解除）：先在 AI 教练页确认处理，再共同确认重排。'
            : '⏸️ 医疗许可未确认：训练处方暂停，请先确认医嘱。'}
        </div>
      )}

      {brief.due_review_notes.length > 0 && (
        <Card title="待复核">
          <p className="text-sm text-amber-300">
            有 {brief.due_review_notes.length} 条教练笔记到了复核时点，去
            <Link to="/coach" className="mx-1 underline">AI 教练</Link>
            确认是否仍然适用。
          </p>
        </Card>
      )}
      {brief.due_review_trials.length > 0 && (
        <Card title="个人尝试复盘">
          <p className="text-sm text-amber-300">
            尝试 #{brief.due_review_trials.join('、#')} 到了复盘时点，去
            <Link to="/mine" className="mx-1 underline">我的</Link>
            查看并决定保持/调整/停止。
          </p>
        </Card>
      )}

      <Card title={`今天 · ${weekday}`}
            right={todayPlan ? <Tag tone="blue">{todayPlan.focus}</Tag> : undefined}>
        {session && session.date === new Date().toISOString().slice(0, 10) ? (
          <div>
            <p className="text-sm text-neutral-300">有一个进行中的训练（{session.day}），未完成 {session.entries.reduce((n, e) => n + e.logged.filter((l) => !l.warmup).length, 0)} 组。</p>
            <button className="btn-primary mt-3 w-full"
                    onClick={() => navigate(`/workout/${encodeURIComponent(session.day)}`)}>
              继续训练
            </button>
          </div>
        ) : todayPlan ? (
          <div>
            <ul className="space-y-1.5">
              {todayPlan.exercises.map((ex, i) => (
                <li key={i} className="flex items-center justify-between text-sm">
                  <span>{ex.name}</span>
                </li>
              ))}
            </ul>
            {brief.plan_fenced ? (
              <p className="mt-3 text-xs text-red-300">
                计划已隔离：旧动作安排暂不能执行，处理安全记录并确认重排后恢复。
              </p>
            ) : (
              <button className="btn-primary mt-3 w-full"
                      onClick={() => navigate(`/workout/${encodeURIComponent(todayPlan.day)}`)}>
                开始训练
              </button>
            )}
          </div>
        ) : (
          <Empty>今天没有安排训练，休息也是训练的一部分。</Empty>
        )}
      </Card>

      {plan && !brief.plan_fenced && (
        <Card title="本周计划" right={<Link to="/training" className="text-xs text-accent">管理</Link>}>
          <p className="text-xs text-neutral-500">{plan.content.template}</p>
          <ul className="mt-2 space-y-1 text-sm">
            {plan.content.schedule.map((d) => (
              <li key={d.day} className="flex justify-between">
                <span className={d.day === weekday ? 'text-accent' : ''}>{d.day} · {d.focus}</span>
                {!brief.plan_fenced && (
                  <button className="text-xs text-neutral-400 underline"
                          onClick={() => navigate(`/workout/${encodeURIComponent(d.day)}`)}>
                    练这天
                  </button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title="最近执行">
        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div><p className="text-lg font-semibold">{brief.sessions_last_7_days}</p><p className="text-xs text-neutral-500">本周已练</p></div>
          <div><p className="text-lg font-semibold">{brief.days_since_last_training ?? '—'}</p><p className="text-xs text-neutral-500">距上次（天）</p></div>
          <div><p className="text-lg font-semibold">{brief.open_pain_flags}</p><p className="text-xs text-neutral-500">待跟进安全记录</p></div>
        </div>
        <Link to="/history" className="mt-2 block text-center text-xs text-accent">查看训练历史</Link>
      </Card>
    </div>
  )
}
