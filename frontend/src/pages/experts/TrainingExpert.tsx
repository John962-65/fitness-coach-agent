import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Activity, MessageCircleHeart } from 'lucide-react'
import { api, ApiError } from '../../api'
import {
  Empty, ErrorBox, PageHeader, Segmented, Spinner, Stat,
} from '../../components/Bits'
import EvidencePanel from '../../components/experts/EvidencePanel'
import ExpertTaskStatus from '../../components/experts/ExpertTaskStatus'
import InsightCard from '../../components/experts/InsightCard'
import RecommendationOptions from '../../components/experts/RecommendationOptions'
import { CONFIDENCE, SPECIALIST_LABEL } from '../../lib/experts'
import { useApp } from '../../store'
import {
  Checkin, Consultation, ExpertInsight, ExpertInsightSummary, ExpertTask,
  PeriodSummary,
} from '../../types'

type Tab = 'overview' | 'data' | 'analysis' | 'advice' | 'consult'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: '概览' },
  { value: 'data', label: '数据' },
  { value: 'analysis', label: '分析' },
  { value: 'advice', label: '建议' },
  { value: 'consult', label: '咨询' },
]

export default function TrainingExpert() {
  const uid = useApp((s) => s.uid)
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(params.get('insight') ? 'analysis' : 'overview')
  const [period, setPeriod] = useState<PeriodSummary | null>(null)
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [tasks, setTasks] = useState<ExpertTask[]>([])
  const [checkins, setCheckins] = useState<Checkin[]>([])
  const [consults, setConsults] = useState<Consultation[]>([])
  const [detail, setDetail] = useState<ExpertInsight | null>(null)
  const [error, setError] = useState('')

  const selectedId = params.get('insight') ?? ''

  const load = useCallback(() => {
    Promise.all([
      api.periodSummary(uid, 30).catch(() => null),
      api.expertInsights(uid, { specialist: 'training_science', limit: 20 }),
      api.expertTasks(uid, { specialist: 'training_science' }),
      api.checkins(uid, 15).catch(() => ({ checkins: [] as Checkin[] })),
      api.consultations(uid, 10).catch(() => ({ consultations: [] as Consultation[] })),
    ]).then(([p, i, t, c, k]) => {
      setPeriod(p)
      setInsights(i.insights)
      setTasks(t.tasks)
      setCheckins((c.checkins ?? []).filter((x) => x.type === 'training'))
      setConsults((k.consultations ?? []).filter(
        (x) => x.specialists.includes('training_science')))
    }).catch((e) => setError((e as ApiError).message))
  }, [uid])

  useEffect(load, [load])

  // 选中洞察 → 拉详情并标记已读（用户明确点开了它）
  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    api.expertInsight(uid, selectedId)
      .then((d) => {
        setDetail(d)
        if (d.status === 'ready') {
          api.markInsightViewed(uid, selectedId)
            .then(() => load()).catch(() => {})
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
  // 建议页使用完整载荷：选中的洞察优先，否则取最新可操作的
  const adviceTargetId = selectedId || actionable?.id || ''
  const [adviceDetail, setAdviceDetail] = useState<ExpertInsight | null>(null)
  useEffect(() => {
    setAdviceDetail(null)
    if (tab !== 'advice' || !adviceTargetId) return
    api.expertInsight(uid, adviceTargetId)
      .then(setAdviceDetail)
      .catch((e) => setError((e as ApiError).message))
  }, [tab, adviceTargetId, uid])

  if (error && !insights.length) {
    return <div className="pt-4"><ErrorBox message={error} onRetry={load} /></div>
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="训练科学工作台"
        sub="训练计划、进阶、负荷与周期 · 数据同源自「我的表现/周期统计」"
        right={<span className="tag bg-accent-soft text-accent-deep">
          <Activity size={13} /> 顾问
        </span>} />

      <div className="mb-4">
        <Segmented value={tab} onChange={setTab} options={TABS} />
      </div>

      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      {/* ---- 概览 ---- */}
      {tab === 'overview' && (
        !period ? <Spinner /> : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat value={period.sessions} label="30 天训练次数" />
              <Stat value={period.working_sets} label="30 天正式组" />
              <Stat value={period.volume.toLocaleString()} label="30 天容量(kg)" />
              <Stat value={period.per_week} label="周频率" />
            </div>
            <div className="card">
              <p className="text-sm font-semibold">当前状态</p>
              {period.sessions === 0 ? (
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  近 30 天还没有训练记录。完成一次训练并保存后，这里会自动出现
                  可追溯的训练后回顾（不需要打开聊天）。
                </p>
              ) : actionable ? (
                <div className="mt-2">
                  <InsightCard insight={actionable}
                               onClick={() => { select(actionable.id); setTab('analysis') }} />
                </div>
              ) : (
                <p className="mt-2 text-[13px] leading-relaxed text-muted">
                  近期分析已处理完毕（忽略/失效的历史在「分析」页可见）。
                  保存新的训练后会自动生成新回顾。
                </p>
              )}
            </div>
            <div className="card">
              <p className="text-sm font-semibold">分析口径（可复核）</p>
              <ul className="mt-2 space-y-1 text-xs leading-relaxed text-muted">
                <li>· 数值与「我的表现」「周期统计」同源同口径（fact_service）</li>
                <li>· e1RM 为 Epley 公式估算值（1-12 次区间），非实测极限</li>
                <li>· 置信度按数据充分性规则生成：窗口会话数 / 纠错 / 记录间隔</li>
                <li>· 引用旧数据的分析在你纠错或计划变更后自动失效，不冒充最新结论</li>
              </ul>
            </div>
          </div>
        )
      )}

      {/* ---- 数据 ---- */}
      {tab === 'data' && (
        <div className="space-y-4">
          <div className="card">
            <p className="text-sm font-semibold">近期训练记录</p>
            {checkins.length === 0 ? (
              <p className="mt-2 text-[13px] text-muted">近 30 天没有训练打卡。</p>
            ) : (
              <ul className="mt-1 divide-y divide-line">
                {checkins.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 py-2.5 text-[13px]">
                    <span className="min-w-0 truncate">
                      #{c.id} {(c.data.exercises ?? []).map((e) => e.name).join('、')}
                    </span>
                    <span className="shrink-0 text-xs text-muted">
                      {c.at.slice(0, 10)}
                      {c.revision > 0 && <span className="ml-1 text-amber-700">（已纠错 r{c.revision}）</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-2 text-2xs text-faint">
              记录纠错入口在「训练 → 历史与统计」；纠错后引用它的分析会标记失效。
            </p>
          </div>
          {tasks.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-semibold">分析任务执行记录</p>
              {tasks.map((t) => <ExpertTaskStatus key={t.id} task={t} />)}
            </div>
          )}
        </div>
      )}

      {/* ---- 分析 ---- */}
      {tab === 'analysis' && (
        <div className="space-y-4">
          {insights.length === 0 ? (
            <Empty icon={<Activity size={22} />} title="还没有分析">
              保存一次训练后会自动生成训练后回顾；分析需要至少一条含正式组的训练记录。
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
                    <span className={`tag ${CONFIDENCE[detail.confidence]?.tone ?? ''}`}>
                      {CONFIDENCE[detail.confidence]?.label ?? detail.confidence}
                    </span>
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
                  {detail.input_refs?.checkin_id && (
                    <p className="mt-3 text-2xs text-faint">
                      分析对象：打卡 #{detail.input_refs.checkin_id}
                      {detail.source_revision.plan_version != null
                        ? ` · 依据计划 v${detail.source_revision.plan_version}` : ''}
                      {' '}· 数据来源 {Object.keys(detail.source_revision.checkins ?? {})
                        .map((id) => `打卡 #${id}`).join('、') || '—'}
                      {Object.values(detail.source_revision.checkins ?? {}).some((r) => r > 0)
                        ? `（含已纠错记录，按当时版本分析）` : ''}
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ---- 建议 ---- */}
      {tab === 'advice' && (
        !adviceTargetId ? (
          <Empty icon={<Activity size={22} />} title="暂无可选方案">
            没有待处理的训练科学分析。先在「分析」页查看结果，或保存一次训练生成新回顾。
          </Empty>
        ) : !adviceDetail ? (
          <Spinner label="加载方案…" />
        ) : (
          <RecommendationOptions insight={adviceDetail}
                                 onChanged={() => { load() }} />
        )
      )}

      {/* ---- 咨询 ---- */}
      {tab === 'consult' && (
        <div className="space-y-4">
          <Link to="/experts/chat" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
              <MessageCircleHeart size={21} className="text-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">向主教练提问</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                聊天是工作台的辅助：咨询会自动附带你的训练事实（可追溯）
              </p>
            </div>
          </Link>
          {consults.length === 0 ? (
            <p className="card text-[13px] leading-relaxed text-muted">
              还没有涉及训练科学的咨询记录。常见问题示例：最近卧推没进步怎么办；
              总结一下这两周练得怎么样。
            </p>
          ) : (
            <div className="space-y-3">
              {consults.map((k) => {
                const advice = k.advices.find((a) => a.specialist === 'training_science')
                return (
                  <div key={k.id} className="card">
                    <p className="text-[13px] font-semibold leading-snug">{k.question}</p>
                    {advice && (
                      <div className="mt-2">
                        <p className="text-xs font-medium text-accent-deep">
                          {SPECIALIST_LABEL.training_science}意见
                        </p>
                        <ul className="mt-1 space-y-1 text-xs leading-relaxed text-muted">
                          {(advice.options ?? []).map((o, i) => (
                            <li key={i}>· {o.title}：{o.detail}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <p className="mt-2 text-2xs text-faint">
                      {k.at.slice(0, 16).replace('T', ' ')} · 完整记录见主教练对话
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
