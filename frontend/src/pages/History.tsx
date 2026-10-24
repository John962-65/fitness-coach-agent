import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { Checkin } from '../types'

export default function History() {
  const uid = useApp((s) => s.uid)
  const [checkins, setCheckins] = useState<Checkin[] | null>(null)
  const [error, setError] = useState('')
  const [correcting, setCorrecting] = useState<Checkin | null>(null)

  const load = useCallback(() => {
    api.checkins(uid, 20).then((r) => setCheckins(r.checkins)).catch((e) => setError(e.message))
  }, [uid])
  useEffect(() => { load() }, [load])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!checkins) return <Spinner />

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="训练历史" sub="最近 20 条 · 点开可纠错（保留修订痕迹）" />
      {checkins.length === 0 && <Empty>还没有记录，完成第一次训练后会出现在这里。</Empty>}
      {checkins.map((c) => (
        <Card key={c.id}
              title={c.type === 'training' ? '训练' : c.type === 'body' ? '身体' : '饮食'}
              right={<div className="flex items-center gap-2">
                {c.revision > 0 && <Tag tone="amber">修订 v{c.revision}</Tag>}
                <span className="text-xs text-neutral-500">{(c.at || '').slice(0, 10)}</span>
              </div>}>
          {c.type === 'training' && c.data.exercises?.length ? (
            <ul className="space-y-1 text-sm">
              {c.data.exercises.map((ex, i) => (
                <li key={i} className="flex justify-between">
                  <span>{ex.name}</span>
                  <span className="text-neutral-400">
                    {ex.sets ? `${ex.sets}组 · ` : ''}{ex.weight_kg ?? '—'}kg × {ex.reps ?? '—'}
                    {ex.rpe ? ` RPE${ex.rpe}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-neutral-400">{String(c.data.raw || JSON.stringify(c.data)).slice(0, 120)}</p>
          )}
          <button className="mt-2 text-xs text-accent underline"
                  onClick={() => setCorrecting(c)}>纠错这条记录</button>
        </Card>
      ))}
      {correcting && (
        <CorrectModal checkin={correcting} uid={uid}
          onClose={() => setCorrecting(null)} onSaved={() => { setCorrecting(null); load() }} />
      )}
    </div>
  )
}

function CorrectModal({ checkin, uid, onClose, onSaved }: {
  checkin: Checkin; uid: string; onClose: () => void; onSaved: () => void
}) {
  const [rows, setRows] = useState((checkin.data.exercises || []).map((ex) => ({
    name: ex.name, weight: ex.weight_kg != null ? String(ex.weight_kg) : '',
    reps: ex.reps != null ? String(ex.reps) : '',
  })))
  const [reason, setReason] = useState('')
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)
  const [saving, setSaving] = useState(false)

  const save = async () => {
    setSaving(true); setError(null)
    try {
      await api.correctCheckin(uid, checkin.id, {
        expected_revision: checkin.revision,
        data: {
          exercises: rows.map((r) => ({
            name: r.name,
            weight_kg: r.weight === '' ? undefined : Number(r.weight),
            reps: r.reps === '' ? undefined : Number(r.reps),
          })),
          raw: checkin.data.raw,
        },
        reason: reason || '修正记录',
        evidence: `本人确认第 ${checkin.id} 条记录有误并修正`,
      })
      onSaved()
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/70" onClick={onClose}>
      <div className="max-h-[85vh] w-full overflow-y-auto rounded-t-2xl bg-neutral-900 p-4"
           onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">纠错 #{checkin.id}（当前修订 v{checkin.revision}）</h3>
          <button className="text-neutral-400" onClick={onClose}>关闭</button>
        </div>
        {error && <div className="mb-3"><ErrorBox message={error.message} details={error.details} /></div>}
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-[1fr_70px_60px] gap-1.5">
              <input className="input !px-2 text-xs" value={r.name} disabled />
              <input className="input !px-2 text-xs" value={r.weight} inputMode="decimal" placeholder="kg"
                     onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, weight: e.target.value } : x))} />
              <input className="input !px-2 text-xs" value={r.reps} inputMode="numeric" placeholder="次"
                     onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, reps: e.target.value } : x))} />
            </div>
          ))}
          <div>
            <label className="label">纠错原因（必填，与原记录一起留档）</label>
            <input className="input" value={reason} placeholder="例如：重量记错了，实际 85"
                   onChange={(e) => setReason(e.target.value)} />
          </div>
          <button className="btn-primary w-full" disabled={saving} onClick={save}>
            {saving ? '保存中…' : '保存纠错'}
          </button>
          <p className="text-[11px] text-neutral-500">
            原值会保留在修订历史里，不会覆盖；派生指标（e1RM/最近重量）会自动重算。
          </p>
        </div>
      </div>
    </div>
  )
}
