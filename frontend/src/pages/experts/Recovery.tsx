import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BedDouble, MessageCircleHeart, Plus } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Empty, ErrorBox, PageHeader, Segmented, Spinner } from '../../components/Bits'
import { Sparkline } from '../../components/charts'
import EvidencePanel from '../../components/experts/EvidencePanel'
import InsightCard from '../../components/experts/InsightCard'
import RecommendationOptions from '../../components/experts/RecommendationOptions'
import RecoveryQuickCheckin from '../../components/recovery/RecoveryQuickCheckin'
import { RECOVERY_SCALES, scaleText } from '../../lib/recovery'
import { useApp } from '../../store'
import type {
  ExpertInsight, ExpertInsightSummary, ExpertTask, RecoveryBrief, RecoverySummary,
} from '../../types'

type Tab = 'today' | 'history' | 'analysis' | 'advice' | 'consult'

const TABS: { value: Tab; label: string }[] = [
  { value: 'today', label: '今日状态' },
  { value: 'history', label: '趋势' },
  { value: 'analysis', label: '分析' },
  { value: 'advice', label: '建议' },
  { value: 'consult', label: '咨询' },
]

/** 恢复顾问工作台（P2）：今日状态 → 快速记录 → 历史趋势 → 分析 → 建议 → 咨询 */
export default function Recovery() {
  const uid = useApp((s) => s.uid)
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(params.get('insight') ? 'analysis' : 'today')
  const [summary, setSummary] = useState<RecoverySummary | null>(null)
  const [brief, setBrief] = useState<RecoveryBrief | null>(null)
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [tasks, setTasks] = useState<ExpertTask[]>([])
  const [detail, setDetail] = useState<ExpertInsight | null>(null)
  const [adviceDetail, setAdviceDetail] = useState<ExpertInsight | null>(null)
  const [checkinOpen, setCheckinOpen] = useState(false)
  const [error, setError] = useState('')

  const selectedId = params.get('insight') ?? ''
  const today = new Date().toISOString().slice(0, 10)
  const hasToday = Boolean(summary?.records.some((r) => r.local_date === today))

  const load = useCallback(() => {
    Promise.all([
      api.recoverySummary(uid, 14),
      api.recoveryBrief(uid),
      api.expertInsights(uid, { specialist: 'recovery', limit: 20 }),
      api.expertTasks(uid, { specialist: 'recovery' }),
    ]).then(([s, b, i, t]) => {
      setSummary(s); setBrief(b); setInsights(i.insights); setTasks(t.tasks)
    }).catch((e) => setError((e as ApiError).message))
  }, [uid])
  useEffect(load, [load])

  useEffect(() => {
    if (!selectedId) { setDetail(null); return }
    api.expertInsight(uid, selectedId).then((d) => {
      setDetail(d)
      if (d.status === 'ready') {
        api.markInsightViewed(uid, selectedId).then(() => load()).catch(() => {})
      }
    }).catch((e) => setError((e as ApiError).message))
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

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="恢复工作台"
        sub="睡眠、疲劳、酸痛（自报 1-5）× 训练负荷 · 无综合评分，观察即观察"
        right={<span className="tag bg-accent-soft text-accent-deep">
          <BedDouble size={13} /> 顾问
        </span>} />
      <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      {/* ---- 今日状态 ---- */}
      {tab === 'today' && (!summary || !brief ? <Spinner /> : (
        <div className="space-y-4">
          {/* 训练前简报（确定性） */}
          <div className={`card border-2 ${brief.stance === 'restricted'
            ? 'border-red-300 bg-red-50/70'
            : brief.stance === 'caution' ? 'border-amber-200 bg-amber-50/70' : ''}`}>
            <p className="text-sm font-semibold">训练前简报</p>
            <p className={`mt-1 text-[13px] font-medium leading-relaxed ${
              brief.stance === 'restricted' ? 'text-red-700'
              : brief.stance === 'caution' ? 'text-amber-800' : 'text-ink'}`}>
              {brief.headline}
            </p>
            {brief.signals.length > 0 && (
              <p className="mt-1 text-xs text-muted">信号：{brief.signals.join('；')}</p>
            )}
            {brief.restrictions.length > 0 && (
              <p className="mt-1 text-xs text-red-700">{brief.restrictions.join('；')}</p>
            )}
            {brief.observations.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs leading-relaxed text-muted">
                {brief.observations.map((o, i) => <li key={i}>· {o}</li>)}
              </ul>
            )}
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {brief.options.map((o) => (
                <span key={o.option_id}
                      className="rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-medium">
                  {o.title}
                </span>
              ))}
            </div>
            <p className="mt-2 text-2xs leading-relaxed text-faint">{brief.note}</p>
          </div>

          {/* 今日打卡 */}
          <div className="card">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">今日恢复记录</p>
              <button className="btn-soft btn text-xs" onClick={() => setCheckinOpen(true)}>
                <Plus size={14} /> {hasToday ? '更新今日' : '快速打卡（30 秒）'}
              </button>
            </div>
            {hasToday ? (
              <ul className="mt-2 space-y-0.5 text-[13px] leading-relaxed">
                {(() => {
                  const r = summary.records.find((x) => x.local_date === today)!
                  return (
                    <>
                      <li>睡眠时长：{r.sleep_hours != null ? `${r.sleep_hours} 小时` : '未记录'}</li>
                      {RECOVERY_SCALES.map((s) => (
                        <li key={s.key}>{s.label}：{scaleText(s.key, r[s.key as 'fatigue'])}</li>
                      ))}
                      {r.soreness_regions.length > 0 && <li>酸痛区域：{r.soreness_regions.join('、')}</li>}
                      {r.notes && <li className="text-muted">备注：{r.notes}</li>}
                      {r.revision > 0 && <li className="text-2xs text-amber-700">已修订 r{r.revision}</li>}
                    </>
                  )
                })()}
              </ul>
            ) : (
              <p className="mt-2 text-[13px] leading-relaxed text-muted">
                今天还没有记录。所有字段可选，记一项也行——连续记录几天后，
                这里会出现有依据的恢复观察（没有数据时不会编）。
              </p>
            )}
          </div>

          {/* 数据完整性 */}
          <div className="card">
            <p className="text-sm font-semibold">数据完整性（近 14 天）</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">
              有 {summary.records_count} 天恢复记录。
              {Object.entries(summary.data_quality).map(([k, v]) => (
                <span key={k} className="ml-2 text-amber-700">{v}</span>
              ))}
            </p>
            {summary.limitations.length > 0 && (
              <ul className="mt-1.5 space-y-0.5 text-xs leading-relaxed text-faint">
                {summary.limitations.map((l, i) => <li key={i}>· {l}</li>)}
              </ul>
            )}
          </div>
        </div>
      ))}

      {/* ---- 历史趋势 ---- */}
      {tab === 'history' && (!summary ? <Spinner /> : (
        <div className="space-y-4">
          {RECOVERY_SCALES.filter((s) => s.key !== 'sleep_quality').map((scale) => {
            const pts = [...summary.records]
              .sort((a, b) => a.local_date.localeCompare(b.local_date))
              .filter((r) => r[scale.key as 'fatigue'] != null)
              .map((r) => ({ label: r.local_date.slice(5),
                             value: r[scale.key as 'fatigue'] as number }))
            return (
              <div key={scale.key} className="card">
                <p className="text-sm font-semibold">{scale.label}变化</p>
                {pts.length < 2 ? (
                  <p className="mt-2 text-xs text-muted">
                    记录不足两次，暂无趋势（只显示实际数据点，不强行拟合）。
                  </p>
                ) : (
                  <Sparkline points={pts} unit=" 分" height={72} />
                )}
              </div>
            )
          })}
          <div className="card">
            <p className="text-sm font-semibold">睡眠时长变化</p>
            {(() => {
              const pts = [...summary.records]
                .sort((a, b) => a.local_date.localeCompare(b.local_date))
                .filter((r) => r.sleep_hours != null)
                .map((r) => ({ label: r.local_date.slice(5), value: r.sleep_hours as number }))
              return pts.length < 2
                ? <p className="mt-2 text-xs text-muted">记录不足两次，暂无趋势。</p>
                : <Sparkline points={pts} unit=" 小时" height={72} />
            })()}
          </div>
          <ul className="card divide-y divide-line text-[13px]">
            {summary.records.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-2">
                <span className="font-medium">{r.local_date.slice(5)}</span>
                <span className="text-xs text-muted">
                  睡眠 {r.sleep_hours ?? '—'}h · 疲劳 {r.fatigue ?? '—'} ·
                  酸痛 {r.muscle_soreness ?? '—'} · 意愿 {r.training_readiness ?? '—'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {/* ---- 分析 ---- */}
      {tab === 'analysis' && (
        <div className="space-y-4">
          {insights.length === 0 ? (
            <Empty icon={<BedDouble size={22} />} title="还没有恢复分析">
              连续记录几天恢复状态并完成训练后，恢复顾问会自动生成
              引用真实记录的回顾（观察≠推断，无综合评分）。
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
                  <h4 className="mb-2 mt-4 text-sm font-semibold">局限</h4>
                  <ul className="space-y-1 text-xs leading-relaxed text-muted">
                    {detail.limitations.map((l, i) => <li key={i}>· {l}</li>)}
                  </ul>
                </div>
              )}
              {tasks.length > 0 && (
                <p className="px-1 text-2xs text-faint">
                  分析任务 {tasks.length} 条（失败 {tasks.filter((t) => t.status === 'failed').length}）；
                  执行日志见专家中心。
                </p>
              )}
            </>
          )}
        </div>
      )}

      {/* ---- 建议 ---- */}
      {tab === 'advice' && (
        !adviceTargetId ? (
          <Empty icon={<BedDouble size={22} />} title="暂无可选方案">
            没有待处理的恢复分析。先记录恢复状态并完成一次训练。
          </Empty>
        ) : !adviceDetail ? <Spinner label="加载方案…" /> : (
          <RecommendationOptions insight={adviceDetail} onChanged={load} />
        )
      )}

      {/* ---- 咨询 ---- */}
      {tab === 'consult' && (
        <div className="card">
          <Link to="/experts/chat" className="flex items-center gap-3.5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
              <MessageCircleHeart size={21} className="text-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">向主教练提问</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                聊天是工作台的辅助；涉及恢复状态的判断一律以这里的真实记录为准
              </p>
            </div>
          </Link>
          <p className="mt-3 rounded-xl bg-canvas p-2.5 text-2xs leading-relaxed text-muted">
            持续疼痛、胸闷、头晕等症状请优先考虑就医评估；康复与伤痛风险辅助
            将在 P3 提供系统化的症状记录与安全分流。
          </p>
        </div>
      )}

      {checkinOpen && (
        <RecoveryQuickCheckin date={today} hasExisting={hasToday}
                              onClose={() => setCheckinOpen(false)} onSaved={load} />
      )}
    </div>
  )
}
