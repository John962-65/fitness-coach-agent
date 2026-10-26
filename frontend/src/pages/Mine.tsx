import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  CalendarRange, ChevronRight, FlaskConical, MapPin, Scale, Settings, Sparkles,
  TriangleAlert,
} from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Empty, ErrorBox, Field, Input, PageHeader, Sheet, Spinner, Tag, Textarea,
} from '../components/Bits'
import { useApp } from '../store'
import { ApproachView, Profile, Trial, TrialObservation, TrialReview } from '../types'

const STRUCTURE_LABEL: Record<string, string> = {
  full_body: '全身', upper_lower: '上下肢分化', ppl: '推拉腿分化',
  circuit: '循环训练', custom: '自定义',
}
const INTENSITY_LABEL: Record<string, string> = {
  linear: '线性进阶', rpe_based: 'RPE 驱动', periodized: '周期化', flexible: '灵活进阶',
}
export const LEVEL_LABEL: Record<string, string> = {
  beginner: '新手', intermediate: '进阶', advanced: '老炮',
}

// 内部枚举 → 自然语言（摘要文本由后端生成，含枚举原值，展示前统一转换）
const ENUM_LABELS: Record<string, string> = {
  muscle_gain: '增肌', fat_loss: '减脂', strength: '力量', health: '健康', shaping: '塑形',
  beginner: '新手', intermediate: '进阶', advanced: '老炮',
  gym: '健身房', home: '居家',
  full_body: '全身', upper_lower: '上下肢分化', ppl: '推拉腿分化',
  circuit: '循环训练', custom: '自定义',
  linear: '线性进阶', rpe_based: 'RPE 驱动', periodized: '周期化', flexible: '灵活进阶',
}
export function humanize(text: string): string {
  return text.replace(/\b[a-z_]+\b/g, (w) => ENUM_LABELS[w] || w)
}

export default function Mine() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [summary, setSummary] = useState('')
  const [view, setView] = useState<ApproachView | null>(null)
  const [trials, setTrials] = useState<Trial[] | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const load = useCallback(() => {
    api.profile(uid).then((r) => { setProfile(r.profile); setSummary(r.summary) })
      .catch((e) => setError(e.message))
    api.approach(uid).then(setView).catch(() => setView({ initialized: false }))
    api.trials(uid).then((r) => setTrials(r.trials)).catch(() => setTrials([]))
  }, [uid])
  useEffect(() => { load() }, [load])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!profile) return <Spinner />

  const a = view?.initialized ? view!.approach! : null
  const level = String(profile.experience?.level || '')

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="我的" sub={`用户 ${uid}`} />

      {/* 资料卡 */}
      <div className="card">
        <div className="flex items-center gap-4">
          <span className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-night text-lg font-bold text-accent">
            {(uid || '?').slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-2 text-lg font-bold">
              {uid}
              {level && <Tag tone="brand">{LEVEL_LABEL[level] || level}</Tag>}
            </p>
            <p className="mt-0.5 text-xs text-muted">
              {profile.goal?.primary ? `目标：${GOAL_LABEL[String(profile.goal.primary)] || profile.goal.primary} · ` : ''}
              {profile.resources?.days_per_week ? `每周 ${profile.resources.days_per_week} 练` : ''}
            </p>
          </div>
        </div>
        {summary && (
          <p className="mt-3 whitespace-pre-wrap rounded-xl bg-canvas p-3.5 text-[13px] leading-relaxed text-ink/90">
            {humanize(summary)}
          </p>
        )}
      </div>

      {/* 我的训练方式 */}
      <div className="card mt-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-[15px] font-semibold">
            <Sparkles size={15} className="text-accent-deep" /> 我的训练方式
          </h2>
          {a && <Tag tone="brand">v{a.revision}</Tag>}
        </div>

        {!a ? (
          <div className="mt-3">
            <Empty title="还没建立训练方式">从现有计划一键初始化，之后可随时修改并保留版本。</Empty>
            <Button variant="ghost" block className="mt-3"
                    onClick={() => api.initApproach(uid).then(() => load()).catch((e: ApiError) => setNote(e.message))}>
              从当前计划初始化
            </Button>
          </div>
        ) : (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-2.5">
              <div className="rounded-xl bg-canvas p-3">
                <dt className="text-2xs text-muted">结构</dt>
                <dd className="mt-0.5 text-sm font-semibold">
                  {STRUCTURE_LABEL[a.structure.value] || a.structure.value}
                </dd>
              </div>
              <div className="rounded-xl bg-canvas p-3">
                <dt className="text-2xs text-muted">强度风格</dt>
                <dd className="mt-0.5 text-sm font-semibold">
                  {INTENSITY_LABEL[a.intensity_style.value] || a.intensity_style.value}
                </dd>
              </div>
              <div className="rounded-xl bg-canvas p-3">
                <dt className="text-2xs text-muted">动作选择</dt>
                <dd className="nums mt-0.5 text-sm font-semibold">{a.exercise_selection.length} 项</dd>
              </div>
              <div className="rounded-xl bg-canvas p-3">
                <dt className="text-2xs text-muted">饮食方式</dt>
                <dd className="mt-0.5 truncate text-sm font-semibold">
                  {a.diet_approach.strategy || a.diet_approach.note || '—'}
                </dd>
              </div>
            </dl>
            {view!.referenced?.active_trial && (
              <p className="mt-2.5 flex items-center gap-1.5 text-xs text-sky-700">
                <FlaskConical size={13} /> 进行中的尝试：{view!.referenced.active_trial.change_desc}
              </p>
            )}
            {view!.referenced?.active_plan && view!.referenced.active_plan.approach_revision != null
              && view!.referenced.active_plan.approach_revision < a.revision && (
              <p className="mt-2 flex items-start gap-1.5 rounded-xl bg-amber-50 p-2.5 text-xs leading-relaxed text-amber-800">
                <TriangleAlert size={14} className="mt-0.5 shrink-0" />
                当前计划基于训练方式 v{view!.referenced.active_plan.approach_revision}，落后于最新 v{a.revision}；
                去 AI 教练页商量是否重排。
              </p>
            )}
            <Button variant="soft" block className="mt-3"
                    onClick={() => navigate('/mine/approach')}>
              查看 / 编辑 · 版本历史 <ChevronRight size={15} />
            </Button>
          </>
        )}
      </div>

      {/* 个人尝试 */}
      <TrialsCard uid={uid} trials={trials} onChanged={load} note={setNote} />
      {note && <p className="mt-2 text-center text-xs text-accent-deep">{note}</p>}

      {/* 入口列表 */}
      <nav className="card mt-4 !p-0" aria-label="更多">
        <ul className="rows">
          {[
            { to: '/history', icon: CalendarRange, label: '训练历史', desc: '最近 20 条记录与纠错' },
            { to: '/mine/locations', icon: MapPin, label: '训练地点与器械', desc: '当前地点、可用器械与自定义器械' },
            { to: '/mine/body', icon: Scale, label: '身体数据', desc: '体重/围度/成分与趋势（P2）' },
            { to: '/mine/approach', icon: Sparkles, label: '训练方式（编辑与版本）', desc: '五维度直改，历史可恢复' },
            { to: '/mine/settings', icon: Settings, label: '设置与数据', desc: '离线同步、导出、访问令牌' },
          ].map((row) => (
            <li key={row.to}>
              <Link to={row.to}
                    className="flex min-h-[60px] items-center gap-3.5 px-4 py-3 transition-colors hover:bg-canvas">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-canvas text-muted">
                  <row.icon size={17} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium">{row.label}</span>
                  <span className="block truncate text-xs text-muted">{row.desc}</span>
                </span>
                <ChevronRight size={16} className="shrink-0 text-faint" />
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      <p className="px-2 pb-2 pt-4 text-2xs leading-relaxed text-faint">
        本系统不提供医疗诊断或治疗建议；涉及伤病、疾病、孕期、用药的内容默认隔离并建议咨询专业人员。
        视频估计与模型推断不构成医学结论。
      </p>
    </div>
  )
}

const GOAL_LABEL: Record<string, string> = {
  fat_loss: '减脂', muscle_gain: '增肌', strength: '力量', health: '健康', shaping: '塑形',
}

/* ---------------- 个人尝试闭环（发起五要素 / 结束复盘 / 草稿预填） ---------------- */

function TrialsCard({ uid, trials, onChanged, note }: {
  uid: string
  trials: Trial[] | null
  onChanged: () => void
  note: (msg: string) => void
}) {
  const active = (trials || []).find((t) => t.status === 'active')
  const history = (trials || []).filter((t) => t.status !== 'active')
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState({ change_desc: '', reason: '', observe: '',
                                       stop_rule: '', review_days: 14, baseline: '' })
  const [ending, setEnding] = useState(false)
  const [outcome, setOutcome] = useState('')
  const [decision, setDecision] = useState<'keep' | 'stop' | 'adjust'>('keep')
  const [error, setError] = useState('')

  // Coach 页"发起尝试"直连草稿（M5 验收链：了解方案 → 选择尝试）
  useEffect(() => {
    const raw = localStorage.getItem('m5-trial-draft')
    if (raw) {
      try { setDraft((d) => ({ ...d, ...JSON.parse(raw) })); setOpen(true) } catch { /* 忽略坏草稿 */ }
      localStorage.removeItem('m5-trial-draft')
    }
  }, [])

  const start = () => {
    setError('')
    api.startTrial(uid, draft)
      .then(() => { setOpen(false); note('尝试已开始：单因素改变，观察期内如实记录'); onChanged() })
      .catch((e: ApiError) => setError(e.message))
  }
  const end = () => {
    if (!active) return
    setError('')
    api.endTrial(uid, active.id, { outcome, decision })
      .then(() => {
        setEnding(false); setOutcome('')
        note(decision === 'keep' ? '已保留该尝试。若它改变了训练方式，去"编辑我的训练方式"固化下来'
          : decision === 'adjust' ? '已记录"调整"结论：想好下一个单因素再开新尝试'
          : '已停止该尝试，回到之前的做法')
        onChanged()
      })
      .catch((e: ApiError) => setError(e.message))
  }

  return (
    <div className="card mt-4">
      <div className="flex items-start justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-[15px] font-semibold">
          <FlaskConical size={15} className="text-accent-deep" /> 个人尝试
        </h2>
        {!active && (
          <button className="btn-sm btn border border-line bg-surface font-medium"
                  onClick={() => setOpen(true)}>
            发起尝试
          </button>
        )}
      </div>

      {error && <div className="mt-2.5"><ErrorBox message={error} /></div>}

      {active ? (
        <div className="mt-3">
          <div className="rounded-xl border border-line bg-canvas p-3.5">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold">{active.change_desc}</p>
              <Tag tone={active.due_review ? 'amber' : 'blue'}>
                {active.due_review ? '该复盘了' : '进行中'}
              </Tag>
            </div>
            <dl className="mt-2 space-y-1 text-xs leading-relaxed text-muted">
              <p>为什么：{active.reason}</p>
              <p>观察：{active.observe}</p>
              <p>停止条件：{active.stop_rule}</p>
              {active.review_at && <p>复盘时点：{active.review_at.slice(0, 10)}</p>}
              {typeof active.baseline === 'string' && active.baseline
  && !active.baseline.trim().startsWith('{')
  && <p>尝试前基线：{active.baseline}</p>}
            </dl>
            {active.exercise_id && (
              <TrialProgress uid={uid} trialId={active.id} due={active.due_review}
                             onChanged={onChanged} note={note} />
            )}
            {ending ? (
              <div className="mt-3 space-y-2.5 rounded-xl border border-line bg-surface p-3">
                <Field label="复盘（必填）：这段时间的感受与执行情况">
                  <Textarea className="min-h-16 text-[13px]" value={outcome}
                            placeholder="例如：前两周睡眠变好，第三周加班没执行好；膝无不适"
                            onChange={(e) => setOutcome(e.target.value)} />
                </Field>
                <div className="flex flex-wrap items-center gap-2">
                  {([['keep', '保留'], ['adjust', '调整'], ['stop', '停止']] as const).map(([v, l]) => (
                    <button key={v} onClick={() => setDecision(v)}
                            className={`tag min-h-9 px-3 ${
                              decision === v ? 'bg-night text-white' : 'border border-line bg-surface text-muted'}`}>
                      {l}
                    </button>
                  ))}
                  <Button size="sm" className="ml-auto" disabled={!outcome.trim()} onClick={end}>提交复盘</Button>
                </div>
              </div>
            ) : (
              <Button variant="ghost" block className="mt-3"
                      onClick={() => setEnding(true)}>
                结束并复盘（保留 / 调整 / 停止）
              </Button>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-2.5 text-xs leading-relaxed text-muted">
          同一时间只试一个变量；五要素（改变/原因/观察/停止条件/复盘周期）缺一不可。
        </p>
      )}

      {history.length > 0 && (
        <ul className="mt-3 space-y-2 border-t border-line pt-3">
          {history.slice(0, 4).map((t) => (
            <li key={t.id} className="rounded-xl bg-canvas p-3 text-xs leading-relaxed">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-ink">{t.change_desc}</span>
                <Tag tone={t.decision === 'keep' ? 'green' : t.decision === 'stop' ? 'neutral' : 'amber'}>
                  {{ keep: '保留', stop: '停止', adjust: '调整' }[t.decision || ''] || t.decision}
                </Tag>
              </div>
              {t.outcome && <p className="mt-0.5 text-muted">复盘：{t.outcome}</p>}
            </li>
          ))}
        </ul>
      )}

      {/* 发起尝试表单（底部抽屉） */}
      <Sheet open={open} onClose={() => setOpen(false)} title="发起一次尝试"
             footer={
               <Button block onClick={start}>开始尝试</Button>
             }>
        <div className="space-y-3">
          <p className="rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
            单因素改变，观察期内如实记录；复盘时决定保留 / 调整 / 停止。
          </p>
          <Field label="改变什么（单一因素）">
            <Input placeholder="如：改上下肢分化" value={draft.change_desc}
                   onChange={(e) => setDraft({ ...draft, change_desc: e.target.value })} />
          </Field>
          <Field label="为什么尝试">
            <Input placeholder="如：每次训练时间太长" value={draft.reason}
                   onChange={(e) => setDraft({ ...draft, reason: e.target.value })} />
          </Field>
          <Field label="观察什么">
            <Input placeholder="如：恢复情况 / 膝不适" value={draft.observe}
                   onChange={(e) => setDraft({ ...draft, observe: e.target.value })} />
          </Field>
          <Field label="何时停止">
            <Input placeholder="如：膝痛立即停" value={draft.stop_rule}
                   onChange={(e) => setDraft({ ...draft, stop_rule: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="复盘周期（天）">
              <Input inputMode="numeric" min={1} max={180} value={draft.review_days}
                     onChange={(e) => setDraft({ ...draft, review_days: Number(e.target.value) })} />
            </Field>
            <Field label="尝试前基线（可选）">
              <Input placeholder="基线感受" value={draft.baseline}
                     onChange={(e) => setDraft({ ...draft, baseline: e.target.value })} />
            </Field>
          </div>
        </div>
      </Sheet>
    </div>
  )
}

/** P5-C3：候选来源尝试的观察进展与复盘决策。
 *  进展/复盘由服务端按真实训练记录确定性生成；任何决策都不自动改计划。 */
function TrialProgress({ uid, trialId, due, onChanged, note }: {
  uid: string
  trialId: number
  due: boolean
  onChanged: () => void
  note: (msg: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<{
    observation: TrialObservation; review?: TrialReview } | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = (withReview: boolean) => {
    setError('')
    api.trialDetail(uid, trialId, withReview)
      .then(setDetail)
      .catch((e: ApiError) => setError(e.message))
  }

  const decide = (decision: 'keep' | 'adjust' | 'stop' | 'observe') => {
    setBusy(true); setError('')
    api.trialDecision(uid, trialId, { decision })
      .then((out) => {
        note(out.note || '已记录你的决定')
        setOpen(false); setDetail(null)
        onChanged()
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setBusy(false))
  }

  if (!open) {
    return (
      <button className="btn-plain mt-2 !px-0 text-xs"
              onClick={() => { setOpen(true); load(due) }}>
        查看观察进展{due ? '与复盘草稿' : ''}
      </button>
    )
  }
  const obs = detail?.observation
  const review = detail?.review
  return (
    <div className="mt-2.5 space-y-2 rounded-xl border border-line bg-surface p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-ink">观察进展</p>
        <button className="text-2xs text-muted underline underline-offset-2"
                onClick={() => { setOpen(false); setDetail(null) }}>收起</button>
      </div>
      {error && <ErrorBox message={error} />}
      {!detail && !error && <Spinner />}
      {obs && (
        <p className="text-xs leading-relaxed text-muted">
          指标 <b className="text-ink">{metricLabel(obs.observation_metric)}</b>：
          观察期内 {obs.sessions_total} 次训练，达成 {obs.sessions_met} 次
          {obs.sessions_unmet > 0 ? `，未达成 ${obs.sessions_unmet} 次` : ''}。
          {obs.due_for_review
            ? '已到达观察条件，可以复盘。'
            : `复盘条件：${obs.min_sessions ? `${obs.min_sessions} 次训练` : ''}`
              + `${obs.review_at ? `或 ${obs.review_at.slice(0, 10)}（先到为准）` : ''}`}
          {obs.plan_changed_since_start && ' · 尝试期间计划版本已变化（存在同期混杂）'}
        </p>
      )}
      {obs && !review && (
        <Button variant="ghost" className="btn-sm" disabled={busy}
                onClick={() => load(true)}>
          生成复盘草稿
        </Button>
      )}
      {review && (
        <div className="space-y-2 text-xs leading-relaxed">
          <div>
            <p className="font-medium text-ink">已观察</p>
            {review.sections.observed.map((line, i) => <p key={i} className="text-muted">· {line}</p>)}
          </div>
          <div>
            <p className="font-medium text-ink">无法确认 / 注意</p>
            {review.sections.unconfirmed.map((line, i) => <p key={i} className="text-muted">· {line}</p>)}
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {review.decision_options.map((o) => (
              <button key={o.decision} disabled={busy}
                      title={o.note}
                      onClick={() => decide(o.decision as 'keep' | 'adjust' | 'stop' | 'observe')}
                      className={`tag min-h-9 px-3 ${
                        o.decision === 'observe' ? 'border border-line bg-surface text-muted'
                          : 'border border-line bg-surface text-ink hover:border-accent-deep/40'}`}>
                {o.label}
              </button>
            ))}
          </div>
          <p className="text-2xs text-faint">{review.decision_note}</p>
        </div>
      )}
    </div>
  )
}

function metricLabel(metric: string): string {
  return ({ 'target-completion': '目标次数达成', 'duration-attainment': '目标时长达成',
            'steady-cardio-seconds': '有氧时长', 'interval-completion': 'HIIT 完整轮次',
            records: '训练记录' } as Record<string, string>)[metric] || metric
}
