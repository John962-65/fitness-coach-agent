import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Scale, TrendingUp } from 'lucide-react'
import { api, ApiError } from '../api'
import { Empty, ErrorBox, Segmented, Spinner, SubHeader } from '../components/Bits'
import { Sparkline } from '../components/charts'
import MeasurementForm from '../components/body/MeasurementForm'
import BodyHistory from '../components/body/BodyHistory'
import { useApp } from '../store'
import type { BodyMeasurement, BodySummary, BodyTrend } from '../types'
import { BODY_METRICS, fmtDelta, fmtNum } from '../lib/body'

const WINDOWS = [
  { value: '7', label: '7 天' }, { value: '30', label: '30 天' },
  { value: '90', label: '90 天' }, { value: '0', label: '全部' },
]

/** 身体数据页（/mine/body）：概览 → 快速记录 → 趋势 → 历史 */
export default function BodyMetrics() {
  const uid = useApp((s) => s.uid)
  const [window, setWindow] = useState('30')
  const [metric, setMetric] = useState('weight_kg')
  const [summary, setSummary] = useState<BodySummary | null>(null)
  const [trend, setTrend] = useState<BodyTrend | null>(null)
  const [measurements, setMeasurements] = useState<BodyMeasurement[]>([])
  const [formOpen, setFormOpen] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    const days = Number(window) || 0
    Promise.all([
      api.bodySummary(uid, days || 3650),
      api.bodyTrend(uid, metric, days),
      api.bodyMeasurements(uid),
    ]).then(([s, t, m]) => {
      setSummary(s); setTrend(t); setMeasurements(m.measurements)
    }).catch((e) => setError((e as ApiError).message))
  }, [uid, window, metric])
  useEffect(load, [load])

  const activeMetric = BODY_METRICS.find((m) => m.key === metric)!

  return (
    <div className="mx-auto w-full max-w-5xl">
      <SubHeader title="身体数据" sub="体重 / 围度 / 身体成分 · 只显示实际测量值"
                 onBack={() => history.back()} />
      {error && <div className="mb-3"><ErrorBox message={error} onRetry={load} /></div>}
      {!summary || !trend ? <Spinner /> : (
        <div className="space-y-4">
          {/* 概览 */}
          <div className="grid grid-cols-3 gap-3">
            {BODY_METRICS.slice(0, 3).map((m) => {
              const lt = summary.latest[m.key]
              const chg = summary.facts.find(
                (f) => f.metric === `${m.key}-change`)?.value
              return (
                <div key={m.key} className="card !p-3 text-center">
                  <p className="text-2xs text-muted">{m.label}</p>
                  <p className="nums mt-0.5 text-xl font-bold">{fmtNum(lt?.value, m.unit)}</p>
                  <p className="text-2xs text-faint">
                    {chg != null ? `窗口变化 ${fmtDelta(chg, m.unit)}` : '—'}
                  </p>
                </div>
              )
            })}
          </div>
          <p className="px-1 text-2xs leading-relaxed text-faint">
            近 {summary.window.label} 有 {summary.measurement_days} 天测量 ·
            共 {summary.total_records} 条记录。成分数据（体脂/肌肉量）为设备估算，
            不同来源不默认可比。
          </p>

          {/* 快速记录 */}
          <button className="btn-primary btn w-full" onClick={() => setFormOpen(true)}>
            <Plus size={16} /> 快速记录一次测量
          </button>

          {/* 趋势（默认体重，可切换指标与窗口） */}
          <div className="card">
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-1.5 text-[15px] font-semibold">
                <TrendingUp size={16} /> 变化趋势
              </h3>
              <Segmented value={window} onChange={setWindow} options={WINDOWS} />
            </div>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {BODY_METRICS.map((m) => (
                <button key={m.key}
                        className={`tag ${metric === m.key ? 'bg-accent-soft text-accent-deep'
                                       : 'bg-ink/5 text-muted'}`}
                        onClick={() => setMetric(m.key)}>{m.label}</button>
              ))}
            </div>
            {trend.points.length === 0 ? (
              <Empty icon={<Scale size={20} />} title={`${activeMetric.label}还没有记录`}>
                记录两次以上即可看到趋势（只显示实际数据点，不强行拟合）。
              </Empty>
            ) : (
              <>
                <Sparkline points={trend.points.map((p) => ({
                  label: p.date.slice(5), value: p.value }))} unit={activeMetric.unit} />
                <p className="mt-1.5 text-2xs leading-relaxed text-faint">{trend.note}</p>
              </>
            )}
          </div>

          {/* 与其他模块联动 */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Link to="/experts/nutrition" className="card text-sm">
              <p className="font-semibold">营养顾问 · 体重 × 饮食目标</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                饮食分析会引用这里的体重趋势（相关观察，非因果判断）
              </p>
            </Link>
            <Link to="/experts/recovery" className="card text-sm">
              <p className="font-semibold">恢复顾问 · 训练前简报</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                结合恢复记录与训练负荷给出当次训练的可选方向
              </p>
            </Link>
          </div>

          {/* 历史 */}
          <div>
            <h3 className="mb-2 text-sm font-semibold">测量历史</h3>
            <BodyHistory measurements={measurements} onChanged={load} />
          </div>
          <p className="px-1 text-2xs leading-relaxed text-faint">
            {summary.limitations.slice(0, 2).map((l, i) => <span key={i}>{l} </span>)}
          </p>
        </div>
      )}
      {formOpen && (
        <MeasurementForm editing={null} onClose={() => setFormOpen(false)} onSaved={load} />
      )}
    </div>
  )
}
