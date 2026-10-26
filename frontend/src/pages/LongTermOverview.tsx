// P8-E：长期成长概览（P7-D 报告的只读呈现；每周/每月/自定义区间）。
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader, ErrorBox, Spinner, Tag, Button } from '../components/Bits'
import { api, ApiError } from '../api'
import { useApp } from '../store'
import type { LongTermReport } from '../types'

const VERDICT_LABELS: Record<string, string> = {
  improving: '上行', stable: '平稳', declining: '下行', insufficient: '数据不足',
}

export default function LongTermOverview() {
  const uid = useApp((s) => s.uid)
  const [period, setPeriod] = useState<'week' | 'month'>('month')
  const [report, setReport] = useState<LongTermReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(() => {
    setLoading(true); setError('')
    api.longTermReport(uid, period)
      .then(setReport)
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }, [uid, period])

  useEffect(() => { load() }, [load])

  return (
    <div className="mx-auto min-h-dvh w-full max-w-xl px-4 pb-10 pt-6">
      <PageHeader title="长期成长概览"
                  sub="真实记录的只读汇总；数据不足处如实说明" />
      <div className="mt-4 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {([['week', '本周'], ['month', '近 30 天']] as const).map(([k, l]) => (
            <button key={k} aria-pressed={period === k}
                    onClick={() => setPeriod(k)}
                    className={`rounded-xl border p-2 text-sm font-medium transition-colors ${
                      period === k ? 'border-accent-deep/50 bg-accent-soft/60'
                                   : 'border-line bg-surface'}`}>
              {l}
            </button>
          ))}
        </div>
        {error && <ErrorBox message={error} />}
        {loading && <Spinner label="汇总各域同源事实…" />}
        {report && (
          <>
            <p className="text-2xs text-faint">
              区间 {report.range.start} ~ {report.range.end}
              （{report.range.days} 天）· {report.note}
            </p>

            <section className="card">
              <h2 className="text-sm font-semibold">训练</h2>
              <div className="nums mt-2 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl bg-canvas p-2.5">
                  <p className="text-lg font-bold">{report.training.days_trained}</p>
                  <p className="text-2xs text-muted">训练天数</p>
                </div>
                <div className="rounded-xl bg-canvas p-2.5">
                  <p className="text-lg font-bold">{report.training.sessions}</p>
                  <p className="text-2xs text-muted">训练次数</p>
                </div>
                <div className="rounded-xl bg-canvas p-2.5">
                  <p className="nums text-lg font-bold">
                    {Math.round(report.training.strength_volume_kg)}</p>
                  <p className="text-2xs text-muted">力量容量 kg</p>
                </div>
              </div>
              <p className="mt-2 text-2xs leading-relaxed text-muted">
                有氧 {report.training.steady_cardio_seconds}s
                {report.training.steady_cardio_distance_m
                  ? ` · ${report.training.steady_cardio_distance_m}m` : ''}
                · HIIT {report.training.interval_sessions} 次
              </p>
              <p className="text-2xs text-faint">{report.training.plan.note}</p>
            </section>

            {report.strength_trends.length > 0 && (
              <section className="card">
                <h2 className="text-sm font-semibold">力量表现趋势</h2>
                <ul className="mt-2 space-y-1.5 text-xs leading-relaxed">
                  {report.strength_trends.map((t) => (
                    <li key={t.exercise_id} className="flex items-start gap-2">
                      <Tag tone={t.verdict === 'improving' ? 'green'
                        : t.verdict === 'declining' ? 'amber' : 'neutral'}>
                        {VERDICT_LABELS[t.verdict] || t.verdict}
                      </Tag>
                      <span className="min-w-0 flex-1 text-muted">
                        {t.exercise_id}（{t.metric}）
                        {t.limitations.length > 0 && (
                          <span className="text-faint">
                            · {t.limitations.join('；')}
                          </span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1.5 text-2xs text-faint">
                  趋势由窗口中位数比较得出；e1RM 为估算口径，非实测极限。
                </p>
              </section>
            )}

            <section className="card">
              <h2 className="text-sm font-semibold">营养与恢复</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                饮食记录 {report.nutrition.days_recorded}
                /{report.nutrition.days_total} 天
                （完整度 {report.nutrition.completeness}）
                · 恢复记录 {report.recovery.records_count} 次
              </p>
              <p className="text-2xs text-faint">{report.nutrition.note}</p>
            </section>

            <section className="card">
              <h2 className="text-sm font-semibold">个人尝试与专家建议</h2>
              {report.trials.length > 0 ? (
                <ul className="mt-1.5 space-y-1 text-xs text-muted">
                  {report.trials.map((t) => (
                    <li key={t.id}>
                      · {t.change_desc}
                      （{t.status === 'active' ? '进行中'
                         : ({ keep: '保留', stop: '停止', adjust: '调整' } as
                            Record<string, string>)[t.decision || ''] || t.decision}）
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-xs text-muted">区间内没有新的个人尝试。</p>
              )}
              <p className="mt-1.5 text-2xs leading-relaxed text-muted">
                专家分析：生成 {report.expert_adoption.insights_generated}、
                已读 {report.expert_adoption.viewed}、忽略{' '}
                {report.expert_adoption.dismissed}、失效{' '}
                {report.expert_adoption.invalidated}
                ；计划修改生效 {report.plan_changes_applied} 次。
              </p>
            </section>

            {report.limitations.length > 0 && (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                <p className="text-xs font-semibold text-amber-800">
                  数据充分性说明
                </p>
                <ul className="mt-1 space-y-0.5 text-2xs leading-relaxed text-amber-800">
                  {report.limitations.map((lim, i) => <li key={i}>· {lim}</li>)}
                </ul>
              </div>
            )}

            <Link to="/mine" className="btn-plain block text-center text-xs">
              ← 返回我的
            </Link>
          </>
        )}
        {!report && !loading && !error && (
          <Button block variant="ghost" onClick={load}>加载报告</Button>
        )}
      </div>
    </div>
  )
}
