import { useState } from 'react'
import { History, Pencil, Trash2 } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Sheet } from '../../components/Bits'
import { BODY_METRICS, METHOD_LABEL, fmtNum } from '../../lib/body'
import MeasurementForm from './MeasurementForm'
import { useApp } from '../../store'
import type { BodyMeasurement } from '../../types'

/** 测量历史列表：编辑 / 删除 / 修订记录查看 */
export default function BodyHistory({ measurements, onChanged }: {
  measurements: BodyMeasurement[]; onChanged: () => void }) {
  const uid = useApp((s) => s.uid)
  const [editing, setEditing] = useState<BodyMeasurement | null>(null)
  const [showRevisions, setShowRevisions] = useState<BodyMeasurement | null>(null)
  const [revisions, setRevisions] = useState<
    { revision: number; reason: string; evidence: string; created_at: string }[]>([])
  const [error, setError] = useState('')

  async function remove(m: BodyMeasurement) {
    setError('')
    try {
      await api.deleteBodyMeasurement(uid, m.id)
      onChanged()
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  async function openRevisions(m: BodyMeasurement) {
    setShowRevisions(m)
    try {
      const r = await api.bodyMeasurementRevisions(uid, m.id)
      setRevisions(r.revisions)
    } catch { setRevisions([]) }
  }

  return (
    <div className="space-y-2">
      {error && <ErrorBox message={error} />}
      {measurements.length === 0 ? (
        <p className="card text-sm text-muted">还没有测量记录。</p>
      ) : (
        <ul className="card divide-y divide-line">
          {measurements.map((m) => (
            <li key={m.id} className="py-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium">
                    {m.local_date}
                    {m.revision > 0 && (
                      <span className="ml-1.5 text-2xs text-amber-700">已修订 r{m.revision}</span>
                    )}
                    {m.migrated_from && (
                      <span className="ml-1.5 text-2xs text-faint">（旧记录迁移）</span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted">
                    {BODY_METRICS.filter((k) => m[k.key] != null)
                      .map((k) => `${k.label} ${fmtNum(m[k.key], k.unit)}`).join(' · ') || '—'}
                    {m.measurement_method && ` · ${METHOD_LABEL[m.measurement_method] ?? m.measurement_method}`}
                    {m.device_source ? `（${m.device_source}）` : ''}
                  </p>
                  {m.notes && <p className="mt-0.5 truncate text-2xs text-faint">{m.notes}</p>}
                </div>
                <div className="flex shrink-0 gap-1">
                  <button className="btn btn-ghost size-8 p-0 text-muted" aria-label={`编辑 ${m.local_date}`}
                          onClick={() => setEditing(m)}>
                    <Pencil size={14} />
                  </button>
                  {m.revision > 0 && (
                    <button className="btn btn-ghost size-8 p-0 text-muted"
                            aria-label={`查看修订 ${m.local_date}`}
                            onClick={() => openRevisions(m)}>
                      <History size={14} />
                    </button>
                  )}
                  <button className="btn btn-ghost size-8 p-0 text-red-600"
                          aria-label={`删除 ${m.local_date}`} onClick={() => remove(m)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <MeasurementForm editing={editing}
                         onClose={() => setEditing(null)} onSaved={onChanged} />
      )}
      {showRevisions && (
        <Sheet open title={`修订记录 · ${showRevisions.local_date}`} onClose={() => setShowRevisions(null)}>
          {revisions.length === 0 ? (
            <p className="text-sm text-muted">无修订记录。</p>
          ) : (
            <ul className="space-y-2">
              {revisions.map((r) => (
                <li key={r.revision} className="rounded-xl bg-canvas p-2.5 text-xs leading-relaxed">
                  <p className="font-medium">修订 {r.revision} · {r.created_at.slice(0, 16).replace('T', ' ')}</p>
                  <p className="mt-0.5 text-muted">原因：{r.reason}</p>
                  <p className="text-muted">依据：{r.evidence}</p>
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" block className="mt-3" onClick={() => setShowRevisions(null)}>
            关闭
          </Button>
        </Sheet>
      )}
    </div>
  )
}
