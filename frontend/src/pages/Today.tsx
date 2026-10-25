import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight, ClipboardList, Flame, LineChart, MessageCircleHeart, Play, Plus,
  ShieldAlert, Sparkles,
} from 'lucide-react'
import { api } from '../api'
import {
  CardNight, ErrorBox, Notice, Spinner, Stat,
} from '../components/Bits'
import InsightCard from '../components/experts/InsightCard'
import { useApp } from '../store'
import { ExpertInsightSummary, PlanResponse, RecoveryBrief, TodayBrief } from '../types'

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

function greeting(): string {
  const h = new Date().getHours()
  if (h < 5) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
}

export default function Today() {
  const uid = useApp((s) => s.uid)
  const session = useApp((s) => s.session)
  const offlineCount = useApp((s) => s.offlineCount)
  const [brief, setBrief] = useState<TodayBrief | null>(null)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [recoveryBrief, setRecoveryBrief] = useState<RecoveryBrief | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([api.today(uid), api.plan(uid).catch(() => null)])
      .then(([b, p]) => { setBrief(b); setPlan(p) })
      .catch((e) => setError(e.message))
    // P0：待查看的专业分析卡片（训练完成后自动生成，无需打开聊天）
    api.expertInsights(uid, { status: 'ready', limit: 3 })
      .then((r) => setInsights(r.insights))
      .catch(() => setInsights([]))
    // P2：训练前恢复简报（确定性；有恢复记录或限制时才有内容）
    api.recoveryBrief(uid).then(setRecoveryBrief).catch(() => setRecoveryBrief(null))
  }, [uid])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!brief) return <Spinner />

  const now = new Date()
  const weekday = WEEKDAYS[now.getDay()]
  const dateStr = `${now.getMonth() + 1} 月 ${now.getDate()} 日 · ${weekday}`
  const todayPlan = plan?.content.schedule.find((d) => d.day === weekday)

  // 进行中的会话进度（恢复刷新不丢）
  const continuing = session && session.date === now.toISOString().slice(0, 10)
  const doneSets = continuing
    ? session!.entries.reduce((n, e) => n + e.logged.filter((l) => !l.warmup).length, 0) : 0
  const targetSets = continuing
    ? session!.entries.reduce((n, e) => n + (Number(e.target.sets) || 0), 0) : 0

  const weekGoal = brief.plan_days_per_week ?? 0
  const planDays = brief.plan?.days || []

  return (
    <div className="mx-auto w-full max-w-5xl">
      {/* 问候 + 日期 */}
      <header className="mb-4 flex items-center justify-between gap-3 pt-1">
        <div>
          <p className="text-[13px] text-muted">{dateStr}</p>
          <h1 className="mt-0.5 text-[26px] font-bold leading-tight tracking-tight">
            {greeting()}，{uid}
          </h1>
        </div>
        <Link to="/mine" aria-label="我的"
              className="flex size-11 shrink-0 items-center justify-center rounded-full
                         bg-night text-sm font-bold text-accent">
          {(uid || '?').slice(0, 1).toUpperCase()}
        </Link>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr,320px] lg:gap-6">
        {/* 主列 */}
        <div className="space-y-4">
          {/* 安全隔离 / 医疗暂停（必须足够醒目） */}
          {(brief.plan_fenced || !brief.medical.allows_prescription) && (
            <div className="flex items-start gap-2.5 rounded-2xl border-2 border-red-300 bg-red-50
                            p-4 text-sm font-medium leading-relaxed text-red-700">
              <ShieldAlert size={19} className="mt-0.5 shrink-0" />
              <span>
                {brief.plan_fenced
                  ? '计划已隔离（伤病/安全记录未解除）：先在 AI 教练页确认处理，再共同确认重排。'
                  : '医疗许可未确认：训练处方已暂停，请先确认医嘱。'}
              </span>
            </div>
          )}

          {offlineCount > 0 && (
            <Notice tone="amber">有 {offlineCount} 条离线训练记录待同步，恢复网络后自动补交。</Notice>
          )}

          {/* 今日训练主视觉卡（深色，突出核心操作） */}
          <CardNight className="relative overflow-hidden !p-5 lg:!p-6">
            <div className="pointer-events-none absolute -right-10 -top-14 size-44 rounded-full
                            bg-accent/12 blur-2xl" aria-hidden />
            <div className="relative">
              <div className="flex items-center gap-2">
                <span className="tag bg-accent/15 text-accent">
                  <Sparkles size={13} /> 今日训练
                </span>
                {todayPlan && <span className="text-xs text-white/70">{todayPlan.focus}</span>}
              </div>

              {continuing ? (
                <>
                  <p className="mt-3 text-3xl font-bold leading-tight text-white">
                    {session!.day}
                  </p>
                  <p className="mt-1.5 text-sm text-white/70">
                    有一个进行中的训练 · 已完成 <b className="nums text-accent">{doneSets}</b>
                    /{targetSets || '—'} 组
                  </p>
                  <button className="btn-primary mt-5 w-full text-base"
                          onClick={() => navigate(`/workout/${encodeURIComponent(session!.day)}`)}>
                    <Play size={17} /> 继续训练
                  </button>
                </>
              ) : todayPlan && !brief.plan_fenced ? (
                <>
                  <p className="mt-3 text-3xl font-bold leading-tight text-white">
                    {todayPlan.day} · {todayPlan.focus}
                  </p>
                  <ul className="mt-3 space-y-1.5">
                    {todayPlan.exercises.slice(0, 4).map((ex, i) => (
                      <li key={i} className="flex items-center justify-between gap-3 text-sm">
                        <span className="truncate text-white/85">{ex.name}</span>
                        <span className="nums shrink-0 text-white/60">
                          {ex.sets}×{ex.reps}{ex.weight_kg ? ` · ${ex.weight_kg}kg` : ''}
                        </span>
                      </li>
                    ))}
                    {todayPlan.exercises.length > 4 && (
                      <li className="text-xs text-white/50">
                        还有 {todayPlan.exercises.length - 4} 个动作…
                      </li>
                    )}
                  </ul>
                  <button className="btn-primary mt-5 w-full text-base"
                          onClick={() => navigate(`/workout/${encodeURIComponent(todayPlan.day)}`)}>
                    <Play size={17} /> 开始训练
                  </button>
                </>
              ) : todayPlan ? (
                <>
                  <p className="mt-3 text-3xl font-bold leading-tight text-white">{todayPlan.day} · {todayPlan.focus}</p>
                  <p className="mt-1.5 text-sm leading-relaxed text-white/70">
                    计划已隔离：旧动作安排暂不能执行，处理安全记录并确认重排后恢复。
                  </p>
                  <Link to="/experts/chat" className="btn-soft mt-5 w-full">
                    去 AI 教练处理 <ArrowRight size={16} />
                  </Link>
                </>
              ) : (
                <div className="flex items-start gap-3 py-1">
                  <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-white/10">
                    <Flame size={20} className="text-accent" />
                  </span>
                  <div>
                    <p className="text-lg font-semibold text-white">今天休息</p>
                    <p className="mt-0.5 text-sm leading-relaxed text-white/70">
                      今天没有安排训练，休息也是训练的一部分。
                    </p>
                  </div>
                </div>
              )}
            </div>
          </CardNight>

          {/* 自由训练入口（M6.3：不依赖计划的灵活记录） */}
          <Link to="/workout/free"
                className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border
                           border-dashed border-lineStrong bg-surface/60 text-sm font-medium text-muted
                           transition-colors hover:border-accent-deep/40 hover:text-ink">
            <Plus size={15} /> 自由开始一次训练（不按计划）
          </Link>

          {/* 本周训练进度 */}
          <div className="card">
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-semibold">本周训练</h3>
              <span className="nums text-sm font-semibold text-accent-deep">
                {brief.sessions_last_7_days}<span className="font-normal text-muted">/{weekGoal || '—'} 次</span>
              </span>
            </div>
            <div className="mt-3 flex gap-1.5">
              {WEEKDAYS.map((d) => {
                const planned = planDays.some((p) => p.day === d)
                const isToday = d === weekday
                return (
                  <div key={d} className="flex flex-1 flex-col items-center gap-1">
                    <span className={`flex h-9 w-full items-center justify-center rounded-lg text-xs font-medium
                                      ${isToday ? 'bg-night text-white'
                                      : planned ? 'bg-accent-soft text-accent-deep'
                                      : 'bg-ink/4 text-faint'}`}>
                      {d.slice(1)}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="mt-2.5 text-xs leading-relaxed text-muted">
              最近 7 天已完成 {brief.sessions_last_7_days} 次训练
              {brief.days_since_last_training != null && ` · 距上次 ${brief.days_since_last_training} 天`}
            </p>
          </div>

          {/* 关键指标 */}
          <div className="grid grid-cols-3 gap-3">
            <Stat value={brief.sessions_last_7_days} label="本周已练" />
            <Stat value={brief.days_since_last_training ?? '—'} label="距上次（天）" />
            <Stat value={brief.open_pain_flags} label="待跟进安全记录" tone={brief.open_pain_flags > 0 ? 'warn' : 'default'} />
          </div>

          {/* P2 训练前恢复简报（确定性；仅在有信号/限制/数据时展示） */}
          {recoveryBrief && (recoveryBrief.stance !== 'clear' || recoveryBrief.latest_recovery) && (
            <div className={`card ${recoveryBrief.stance === 'restricted'
              ? 'border-2 border-red-300 bg-red-50/70'
              : recoveryBrief.stance === 'caution' ? 'border-2 border-amber-200 bg-amber-50/70' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">训练前简报</h3>
                <Link to="/experts/recovery" className="text-xs font-medium text-accent-deep hover:underline">
                  恢复工作台
                </Link>
              </div>
              <p className={`mt-1.5 text-[13px] font-medium leading-relaxed ${
                recoveryBrief.stance === 'restricted' ? 'text-red-700'
                : recoveryBrief.stance === 'caution' ? 'text-amber-800' : 'text-ink'}`}>
                {recoveryBrief.headline}
              </p>
              {recoveryBrief.signals.length > 0 && (
                <p className="mt-1 text-xs text-muted">信号：{recoveryBrief.signals.join('；')}</p>
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {recoveryBrief.options.map((o) => (
                  <span key={o.option_id}
                        className="rounded-lg border border-line bg-surface px-2.5 py-1 text-xs font-medium">
                    {o.title}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-2xs text-faint">{recoveryBrief.note}</p>
            </div>
          )}

          {/* P0 专业分析卡片（训练后自动生成，点击直达工作台，不经聊天） */}
          {insights.length > 0 && (
            <div className="space-y-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <LineChart size={16} /> 专业分析
              </h3>
              {insights.map((ins) => (
                <InsightCard key={ins.id} insight={ins}
                             onClick={() => navigate(
                               `/experts/training?insight=${ins.id}`)} />
              ))}
            </div>
          )}

          {/* AI 教练快捷入口 */}
          <Link to="/experts/chat" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft">
              <MessageCircleHeart size={21} className="text-accent-deep" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">问问 AI 教练</p>
              <p className="mt-0.5 truncate text-xs text-muted">
                {brief.due_review_notes.length > 0
                  ? `有 ${brief.due_review_notes.length} 条教练笔记到了复核时点`
                  : '讨论方案 · 解读记录 · 提出修改建议'}
              </p>
            </div>
            <ArrowRight size={18} className="shrink-0 text-muted" />
          </Link>
        </div>

        {/* 侧列（桌面） */}
        <div className="space-y-4">
          {brief.due_review_notes.length > 0 && (
            <div className="card border-amber-200 bg-amber-50/70">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                <ClipboardList size={16} /> 待复核
              </h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-amber-800/90">
                有 {brief.due_review_notes.length} 条教练笔记到了复核时点，去
                <Link to="/experts/chat" className="mx-1 font-semibold underline underline-offset-2">主教练</Link>
                确认是否仍然适用。
              </p>
            </div>
          )}
          {brief.due_review_trials.length > 0 && (
            <div className="card border-amber-200 bg-amber-50/70">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                <ClipboardList size={16} /> 个人尝试复盘
              </h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-amber-800/90">
                尝试 #{brief.due_review_trials.join('、#')} 到了复盘时点，去
                <Link to="/mine" className="mx-1 font-semibold underline underline-offset-2">我的</Link>
                查看并决定保持/调整/停止。
              </p>
            </div>
          )}

          {plan && (
            <div className="card">
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-[15px] font-semibold">本周计划</h3>
                <Link to="/training" className="text-[13px] font-medium text-accent-deep hover:underline">
                  管理
                </Link>
              </div>
              <p className="mb-2 text-xs text-muted">{plan.content.template} · v{plan.version}</p>
              <ul className="rows">
                {plan.content.schedule.map((d) => (
                  <li key={d.day} className="flex items-center justify-between gap-2 py-2.5">
                    <div className="min-w-0">
                      <p className={`text-sm font-medium ${d.day === weekday ? 'text-accent-deep' : ''}`}>
                        {d.day}
                      </p>
                      <p className="truncate text-xs text-muted">{d.focus}</p>
                    </div>
                    {!brief.plan_fenced && (
                      <button className="btn-sm btn shrink-0 border border-line bg-surface"
                              onClick={() => navigate(`/workout/${encodeURIComponent(d.day)}`)}>
                        练这天
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="px-1 text-2xs leading-relaxed text-faint">
            本系统不提供医疗诊断或治疗建议；涉及伤病、疾病、孕期、用药的内容默认隔离并建议咨询专业人员。
          </p>
        </div>
      </div>
    </div>
  )
}
