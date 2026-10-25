import { useEffect, useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { api, ApiError } from '../../api'
import { ErrorBox, PageHeader, Segmented, Spinner } from '../../components/Bits'
import { useApp } from '../../store'
import type { NutritionTrendDay } from '../../types'
import { fmtNutrient } from '../../lib/nutrition'

/** 饮食趋势：7/30/90 天每日已记录合计（未记录日不造 0 行） */
export default function NutritionHistory() {
  const uid = useApp((s) => s.uid)
  const [days, setDays] = useState<7 | 30 | 90>(7)
  const [trend, setTrend] = useState<{ days: NutritionTrendDay[]; note: string } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.nutritionTrends(uid, days).then(setTrend)
      .catch((e) => setError((e as ApiError).message))
  }, [uid, days])

  const max = Math.max(1, ...(trend?.days ?? []).map((d) => d.totals.energy_kcal || 0))

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="饮食趋势" sub="每日已记录摄入量（未记录不代表摄入为 0）" />
      <div className="mb-3">
        <Segmented value={String(days)} onChange={(v) => setDays(Number(v) as 7 | 30 | 90)}
                   options={[{ value: '7', label: '7 天' }, { value: '30', label: '30 天' },
                             { value: '90', label: '90 天' }]} />
      </div>
      {error && <ErrorBox message={error} />}
      {!trend ? <Spinner /> : trend.days.length === 0 ? (
        <p className="card text-sm leading-relaxed text-muted">
          还没有饮食记录。去「饮食」页记录第一餐后，这里会出现趋势。
        </p>
      ) : (
        <ul className="card divide-y divide-line">
          {trend.days.map((d) => (
            <li key={d.local_date} className="py-2.5">
              <div className="flex items-center justify-between gap-2 text-[13px]">
                <span className="flex items-center gap-1.5 font-medium">
                  {d.local_date.slice(5)}
                  {d.complete_mark && <CheckCircle2 size={13} className="text-emerald-600" />}
                </span>
                <span className="nums text-muted">
                  {fmtNutrient(d.totals.energy_kcal)} kcal · 蛋白 {fmtNutrient(d.totals.protein_g)}g
                </span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-canvas">
                <div className="h-full rounded-full bg-accent/70"
                     style={{ width: `${Math.round(((d.totals.energy_kcal || 0) / max) * 100)}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 px-1 text-2xs leading-relaxed text-faint">{trend?.note}</p>
    </div>
  )
}
