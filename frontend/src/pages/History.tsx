import { useCallback, useEffect, useState } from 'react'
import { Dumbbell, Salad, Scale } from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Empty, ErrorBox, Input, PageHeader, Sheet, Spinner, Tag, Textarea,
} from '../components/Bits'
import { buildCorrectedData, ExerciseEdit, SetEdit } from '../lib/checkin'
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
  // M6.1 P0：逐组编辑——set_logs 的每组 weight/reps/rpe 可改，
  // 热身标记与完成时间原样保留；未修改的组按原值回传，绝不丢组。
  const [edits, setEdits] = useState<ExerciseEdit[]>((checkin.data.exercises || []).map((ex) => {
    if (ex.set_logs?.length) {
      return { logs: ex.set_logs.map((l) => ({
        weight: l.weight_kg != null ? String(l.weight_kg) : '',
        reps: l.reps != null ? String(l.reps) : '',
        rpe: l.rpe != null ? String(l.rpe) : '',
      })) }
    }
    return {
      weight: ex.weight_kg != null ? String(ex.weight_kg) : '',
      reps: ex.reps != null ? String(ex.reps) : '',
    }
  }))
  const [reason, setReason] = useState('')
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)
  const [saving, setSaving] = useState(false)

  const patchLog = (ei: number, li: number, patch: Partial<SetEdit>) =>
    setEdits((eds) => eds.map((e, i) => i !== ei ? e : {
      ...e, logs: e.logs!.map((l, j) => (j === li ? { ...l, ...patch } : l)),
    }))
  const patchLegacy = (ei: number, patch: Partial<Pick<ExerciseEdit, 'weight' | 'reps'>>) =>
    setEdits((eds) => eds.map((e, i) => (i === ei ? { ...e, ...patch } : e)))

  const save = async () => {
    setSaving(true); setError(null)
    const data = buildCorrectedData(checkin, edits)
    if (!data) {
      setError({ message: '存在无效的数字输入，请检查重量/次数/RPE' })
      setSaving(false); return
    }
    try {
      await api.correctCheckin(uid, checkin.id, {
        expected_revision: checkin.revision,
        data,
        reason: reason || '修正记录',
        evidence: `本人确认第 ${checkin.id} 条记录有误并修正`,
      })
      onSaved()
    } catch (e) {
      const err = e as ApiError
      setError({ message: err.message, details: err.details })
    } finally { setSaving(false) }
  }

  const hasPerSet = (checkin.data.exercises || []).some((ex) => ex.set_logs?.length)

  return (
    <Sheet open onClose={onClose} title={`纠错 #${checkin.id}（当前修订 v${checkin.revision}）`}
           footer={
             <Button block disabled={saving} onClick={save}>
               {saving ? '保存中…' : '保存纠错'}
             </Button>
           }>
      {error && <div className="mb-3"><ErrorBox message={error.message} details={error.details} /></div>}
      {hasPerSet && (
        <p className="mb-3 rounded-xl bg-accent-soft px-3.5 py-2.5 text-xs leading-relaxed text-accent-deep">
          逐组纠错：只修改需要更正的组；热身标记与完成时间自动保留，
          未修改的组原样保存，原值完整留存于修订历史。
        </p>
      )}
      <div className="space-y-4">
        {(checkin.data.exercises || []).map((ex, ei) => {
          const edit = edits[ei] || {}
          return (
            <div key={ei} className="rounded-xl border border-line bg-canvas p-3">
              <p className="text-sm font-semibold">{ex.name}
                {ex.set_logs?.length ? (
                  <span className="nums ml-1.5 text-xs text-muted">{ex.set_logs.length} 组</span>
                ) : null}
              </p>
              {ex.set_logs?.length ? (
                <div className="mt-2 space-y-1.5">
                  {ex.set_logs.map((l, li) => (
                    <div key={li} className="flex items-center gap-1.5">
                      <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-2xs font-bold ${
                        l.warmup ? 'bg-amber-100 text-amber-700' : 'bg-accent-soft text-accent-deep'}`}>
                        {li + 1}
                      </span>
                      {l.warmup && <span className="tag shrink-0 bg-amber-50 text-amber-700">热身</span>}
                      <Input className="input-sm nums flex-1 text-center" inputMode="decimal"
                             placeholder="kg" aria-label={`第 ${li + 1} 组重量`}
                             value={edit.logs?.[li]?.weight ?? ''}
                             onChange={(e) => patchLog(ei, li, { weight: e.target.value })} />
                      <span className="shrink-0 text-xs text-muted">×</span>
                      <Input className="input-sm nums flex-1 text-center" inputMode="numeric"
                             placeholder="次" aria-label={`第 ${li + 1} 组次数`}
                             value={edit.logs?.[li]?.reps ?? ''}
                             onChange={(e) => patchLog(ei, li, { reps: e.target.value })} />
                      <span className="shrink-0 text-xs text-muted">RPE</span>
                      <Input className="input-sm nums w-14 text-center" inputMode="decimal"
                             placeholder="—" aria-label={`第 ${li + 1} 组 RPE`}
                             value={edit.logs?.[li]?.rpe ?? ''}
                             onChange={(e) => patchLog(ei, li, { rpe: e.target.value })} />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-2 grid grid-cols-2 gap-1.5">
                  <Input className="input-sm nums text-center" inputMode="decimal" placeholder="kg"
                         value={edit.weight ?? ''}
                         onChange={(e) => patchLegacy(ei, { weight: e.target.value })} />
                  <Input className="input-sm nums text-center" inputMode="numeric" placeholder="次"
                         value={edit.reps ?? ''}
                         onChange={(e) => patchLegacy(ei, { reps: e.target.value })} />
                </div>
              )}
            </div>
          )
        })}
        <Textarea className="min-h-14" value={reason}
                  placeholder="纠错原因（必填，与原记录一起留档）。例如：第二组重量记错了，实际 67.5"
                  onChange={(e) => setReason(e.target.value)} />
        <p className="text-xs leading-relaxed text-muted">
          原值会保留在修订历史里，不会覆盖；派生指标（e1RM/最近重量）会按纠正后的记录自动重算。
        </p>
      </div>
    </Sheet>
  )
}
