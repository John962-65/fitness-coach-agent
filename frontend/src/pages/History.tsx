import { useCallback, useEffect, useState } from 'react'
import { Dumbbell, Salad, Scale } from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Empty, ErrorBox, Input, PageHeader, Sheet, Spinner, Tag, Textarea,
} from '../components/Bits'
import { useApp } from '../store'
import { Checkin } from '../types'

const TYPE_META: Record<string, { label: string; icon: typeof Dumbbell }> = {
  training: { label: '训练', icon: Dumbbell },
  body: { label: '身体', icon: Scale },
  diet: { label: '饮食', icon: Salad },
}

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
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="训练历史" sub="最近 20 条 · 点开可纠错（保留修订痕迹）" />

      {checkins.length === 0 && (
        <Empty title="还没有记录">完成第一次训练后，记录会出现在这里。</Empty>
      )}

      <div className="space-y-3">
        {checkins.map((c) => {
          const meta = TYPE_META[c.type] || TYPE_META.training
          return (
            <div key={c.id} className="card">
              <div className="mb-2.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex size-8 items-center justify-center rounded-lg bg-canvas text-muted">
                    <meta.icon size={16} />
                  </span>
                  <span className="text-[15px] font-semibold">{meta.label}</span>
                  {c.revision > 0 && <Tag tone="amber">修订 v{c.revision}</Tag>}
                </div>
                <span className="nums text-xs text-faint">{(c.at || '').slice(0, 10)}</span>
              </div>

              {c.type === 'training' && c.data.exercises?.length ? (
                <ul className="rows">
                  {c.data.exercises.map((ex, i) => (
                    <li key={i} className="py-2 first:pt-0 last:pb-0">
                      {ex.set_logs?.length ? (
                        <div>
                          <p className="text-sm font-medium">
                            {ex.name}
                            <span className="nums ml-1.5 text-xs text-muted">{ex.set_logs.length} 组</span>
                          </p>
                          <ul className="nums mt-1 space-y-0.5">
                            {ex.set_logs.map((l, j) => (
                              <li key={j} className="flex items-center gap-2 text-[13px] text-muted">
                                <span className="w-8 shrink-0 text-faint">#{j + 1}</span>
                                {l.warmup && <span className="tag bg-amber-50 text-amber-700">热身</span>}
                                <span className="text-ink">
                                  {l.weight_kg != null ? `${l.weight_kg} kg` : ''}
                                  {l.weight_kg != null && l.reps != null ? ' × ' : ''}
                                  {l.reps ?? (l.weight_kg != null ? '' : '?')} 次
                                </span>
                                {l.rpe ? <span className="text-faint">RPE {l.rpe}</span> : null}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <div className="flex items-center justify-between text-sm">
                          <span>{ex.name}</span>
                          <span className="nums text-muted">
                            {ex.sets ? `${ex.sets}组 · ` : ''}{ex.weight_kg ?? '—'}kg × {ex.reps ?? '—'}
                            {ex.rpe ? ` RPE${ex.rpe}` : ''}
                          </span>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm leading-relaxed text-muted">
                  {String(c.data.raw || JSON.stringify(c.data)).slice(0, 120)}
                </p>
              )}

              <div className="mt-2.5 flex justify-end border-t border-line pt-2">
                <button className="btn-plain text-accent-deep"
                        onClick={() => setCorrecting(c)}>纠错这条记录</button>
              </div>
            </div>
          )
        })}
      </div>

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
    <Sheet open onClose={onClose} title={`纠错 #${checkin.id}（当前修订 v${checkin.revision}）`}
           footer={
             <Button block disabled={saving} onClick={save}>
               {saving ? '保存中…' : '保存纠错'}
             </Button>
           }>
      {error && <div className="mb-3"><ErrorBox message={error.message} details={error.details} /></div>}
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-[1fr_80px_64px] gap-1.5">
            <Input className="input-sm" value={r.name} disabled />
            <Input className="input-sm" value={r.weight} inputMode="decimal" placeholder="kg"
                   onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, weight: e.target.value } : x))} />
            <Input className="input-sm" value={r.reps} inputMode="numeric" placeholder="次"
                   onChange={(e) => setRows((rs) => rs.map((x, j) => j === i ? { ...x, reps: e.target.value } : x))} />
          </div>
        ))}
        <div className="pt-1">
          <Textarea className="min-h-14" value={reason} placeholder="纠错原因（必填，与原记录一起留档）。例如：重量记错了，实际 85"
                    onChange={(e) => setReason(e.target.value)} />
        </div>
        <p className="text-xs leading-relaxed text-muted">
          原值会保留在修订历史里，不会覆盖；派生指标（e1RM/最近重量）会自动重算。
        </p>
      </div>
    </Sheet>
  )
}
