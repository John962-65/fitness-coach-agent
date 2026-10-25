import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Apple, MessageCircleHeart } from 'lucide-react'
import { api, ApiError } from '../../api'
import {
  Empty, ErrorBox, PageHeader, Segmented, Spinner, Stat,
} from '../../components/Bits'
import EvidencePanel from '../../components/experts/EvidencePanel'
import InsightCard from '../../components/experts/InsightCard'
import RecommendationOptions from '../../components/experts/RecommendationOptions'
import { SPECIALIST_LABEL } from '../../lib/experts'
import { useApp } from '../../store'
import type {
  Consultation, DayNutrition, ExpertInsight, ExpertInsightSummary, ExpertTask,
  NutritionTrendDay,
} from '../../types'
import { fmtNutrient, todayISO } from '../../lib/nutrition'

type Tab = 'overview' | 'data' | 'analysis' | 'advice' | 'consult'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: '概览' },
  { value: 'data', label: '数据' },
  { value: 'analysis', label: '分析' },
  { value: 'advice', label: '建议' },
  { value: 'consult', label: '咨询' },
]

/** 营养顾问工作台（P1）：概览 → 数据 → 分析 → 建议 → 咨询 */
export default function NutritionExpert() {
  const uid = useApp((s) => s.uid)
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(params.get('insight') ? 'analysis' : 'overview')
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [tasks, setTasks] = useState<ExpertTask[]>([])
  const [today, setToday] = useState<DayNutrition | null>(null)
  const [trend, setTrend] = useState<{ days: NutritionTrendDay[]; note: string } | null>(null)
  const [targets, setTargets] = useState<{ energy_kcal: number | null
    protein_g: number | null } | null>(null)
  const [consults, setConsults] = useState<Consultation[]>([])
  const [detail, setDetail] = useState<ExpertInsight | null>(null)
  const [adviceDetail, setAdviceDetail] = useState<ExpertInsight | null>(null)
  const [error, setError] = useState('')

  const selectedId = params.get('insight') ?? ''
  const load = useCallback(() => {
    Promise.all([
      api.expertInsights(uid, { specialist: 'nutrition', limit: 20 }),
      api.expertTasks(uid, { specialist: 'nutrition' }),
      api.dayNutrition(uid, todayISO()),
      api.nutritionTrends(uid, 14),
      api.nutritionTargets(uid).catch(() => null),
      api.consultations(uid, 10).catch(() => ({ consultations: [] as Consultation[] })),
    ]).then(([i, t, d, tr, tg, k]) => {
      setInsights(i.insights)
      setTasks(t.tasks)
      setToday(d)
      setTrend(tr)
      setTargets(tg?.targets ?? null)
      setConsults((k.consultations ?? []).filter(
        (x) => x.specialists.includes('nutrition')))
    }).catch((e) => setError((e as ApiError).message))
  }, [uid])
  useEffect(load, [load])

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    api.expertInsight(uid, selectedId)
      .then((d) => {
        setDetail(d)
        if (d.status === 'ready') {
          api.markInsightViewed(uid, selectedId).then(() => load()).catch(() => {})
        }
      })
      .catch((e) => setError((e as ApiError).message))
  }, [selectedId, uid, load])

  function select(id: string | null) {
    const next = new URLSearchParams(params)
    if (id) next.set('insight', id); else next.delete('insight')
    setParams(next, { replace: true })
  }

  const actionable = insights.find((i) => i.status === 'ready' || i.status === 'viewed')
  const adviceTargetId = selectedId || actionable?.id || ''
  useEffect(() => {
    setAdviceDetail(null)
    if (tab !== 'advice' || !adviceTargetId) return
    api.expertInsight(uid, adviceTargetId).then(setAdviceDetail)
      .catch((e) => setError((e as ApiError).message))
  }, [tab, adviceTargetId, uid])

  const recentDays = trend?.days ?? []
  const recordedDays = recentDays.length
  const completeDays = recentDays.filter((d) => d.complete_mark).length

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="营养工作台" sub="食物、营养目标、饮食分析 · 计算全部由确定性代码完成"
        right={<span className="tag bg-accent-soft text-accent-deep">
          <Apple size={13} /> 顾问
        </span>} />
      <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      {tab === 'overview' && (!today ? <Spinner /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat value={fmtNutrient(today.day.totals.energy_kcal)} label="今日已记录 kcal" />
            <Stat value={fmtNutrient(today.day.totals.protein_g)} label="蛋白质 g" />
            <Stat value={recordedDays} label="14 天有记录天数" />
            <Stat value={completeDays} label="其中标记完整" />
          </div>
          <div className="card">
            <p className="text-sm font-semibold">当前状态</p>
            {today.day.items_count === 0 ? (
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                今天还没有饮食记录。去<Link to="/nutrition"
                  className="mx-1 font-medium text-accent-deep underline underline-offset-2">饮食页</Link>
                记录第一餐后，这里会自动出现饮食回顾（不需要打开聊天）。
              </p>
            ) : actionable ? (
              <div className="mt-2">
                <InsightCard insight={actionable}
                             onClick={() => { select(actionable.id); setTab('analysis') }} />
              </div>
            ) : (
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                近期分析已处理（忽略/失效历史在「分析」页可见）。
              </p>
            )}
          </div>
          <div className="card">
            <p className="text-sm font-semibold">口径说明（可复核）</p>
            <ul className="mt-2 space-y-1 text-xs leading-relaxed text-muted">
              <li>· 只统计「已记录摄入量」：未记录的餐次不当作 0，也不推断</li>
              <li>· 食物营养为内置参考值或你录入的标签（约值），条目保存营养快照</li>
              <li>· 未知营养素保持缺失；方向性建议只在当天记录完整时给出</li>
              <li>· 目标比较使用你自己设置的目标；无目标则只报告摄入量</li>
              <li>· 身体指标联动将在身体与恢复管理（P2）提供</li>
            </ul>
          </div>
        </div>
      ))}

      {tab === 'data' && (
        <div className="space-y-4">
          <div className="card">
            <p className="text-sm font-semibold">今日饮食（{todayISO()}）</p>
            {today && today.meals.length > 0 ? (
              <ul className="mt-1 divide-y divide-line">
                {today.meals.map((m) => (
                  <li key={m.id} className="py-2 text-[13px]">
                    <span className="font-medium">{m.items.map((i) => i.food_name).join('、')}</span>
                    <span className="ml-2 text-xs text-muted">
                      {fmtNutrient(m.totals.energy_kcal)} kcal · 蛋白 {fmtNutrient(m.totals.protein_g)}g
                    </span>
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-[13px] text-muted">今天还没有记录。</p>}
            <div className="mt-2 flex gap-3 text-xs">
              <Link to="/nutrition" className="font-medium text-accent-deep hover:underline">去记录 / 纠错</Link>
              <Link to="/nutrition/targets" className="font-medium text-accent-deep hover:underline">
                目标：{targets?.energy_kcal ? `${targets.energy_kcal} kcal` : '未设置'}
              </Link>
            </div>
          </div>
          {tasks.length > 0 && (
            <div className="card">
              <p className="mb-2 text-sm font-semibold">分析任务（{tasks.length}）</p>
              <ul className="space-y-1.5 text-xs text-muted">
                {tasks.slice(0, 6).map((t) => (
                  <li key={t.id}>
                    [{t.created_at.slice(5, 16)}] {t.trigger_source} → {t.status}
                    {t.error ? `（${t.error}）` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {tab === 'analysis' && (
        <div className="space-y-4">
          {insights.length === 0 ? (
            <Empty icon={<Apple size={22} />} title="还没有饮食分析">
              记录一餐后自动生成饮食回顾；分析只基于已记录数据，不会编造摄入判断。
            </Empty>
          ) : (
            <>
              <div className="space-y-3">
                {insights.map((ins) => (
                  <InsightCard key={ins.id} insight={ins}
                               onClick={() => select(ins.id === selectedId ? null : ins.id)} />
                ))}
              </div>
              {detail && (
                <div className="card">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-semibold">{detail.title}</p>
                    <span className="ml-auto text-2xs text-faint">
                      生成于 {detail.generated_at.slice(0, 16).replace('T', ' ')}
                    </span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-ink/80">{detail.summary}</p>
                  <p className="mt-2 rounded-lg bg-canvas p-2.5 text-xs leading-relaxed text-muted">
                    置信度依据：{detail.confidence_basis}
                  </p>
                  {detail.status_reason && (
                    <p className="mt-2 rounded-lg bg-red-50 p-2.5 text-xs leading-relaxed text-red-700">
                      {detail.status_reason}
                    </p>
                  )}
                  <h4 className="mb-2 mt-4 text-sm font-semibold">发现与证据</h4>
                  <EvidencePanel insight={detail} />
                  {detail.limitations.length > 0 && (
                    <>
                      <h4 className="mb-2 mt-4 text-sm font-semibold">局限</h4>
                      <ul className="space-y-1 text-xs leading-relaxed text-muted">
                        {detail.limitations.map((lim, i) => <li key={i}>· {lim}</li>)}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {tab === 'advice' && (
        !adviceTargetId ? (
          <Empty icon={<Apple size={22} />} title="暂无可选方案">
            没有待处理的饮食分析。先记录饮食，或在「分析」页查看结果。
          </Empty>
        ) : !adviceDetail ? <Spinner label="加载方案…" /> : (
          <RecommendationOptions insight={adviceDetail} onChanged={load} />
        )
      )}

      {tab === 'consult' && (
        <div className="space-y-4">
          <Link to="/experts/chat" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
              <MessageCircleHeart size={21} className="text-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">向主教练提问</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                聊天是工作台的辅助；涉及营养计算的结果一律来自确定性代码
              </p>
            </div>
          </Link>
          {consults.length === 0 ? (
            <p className="card text-[13px] leading-relaxed text-muted">
              还没有涉及营养的咨询记录。示例：增肌期蛋白质怎么安排比较现实；
              不想精确计算热量有什么办法。
            </p>
          ) : (
            <div className="space-y-3">
              {consults.map((k) => {
                const advice = k.advices.find((a) => a.specialist === 'nutrition')
                return (
                  <div key={k.id} className="card">
                    <p className="text-[13px] font-semibold leading-snug">{k.question}</p>
                    {advice && (
                      <ul className="mt-1.5 space-y-1 text-xs leading-relaxed text-muted">
                        {(advice.options ?? []).map((o, i) => <li key={i}>· {o.title}：{o.detail}</li>)}
                      </ul>
                    )}
                    <p className="mt-2 text-2xs text-faint">
                      {k.at.slice(0, 16).replace('T', ' ')} · {SPECIALIST_LABEL.nutrition}
                    </p>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
