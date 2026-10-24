import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ErrorBox, PageHeader, Spinner } from '../components/Bits'
import ExercisePicker from '../components/ExercisePicker'
import { addExercise, editPrescription, removeByIndex, renameDay,
         replaceByIndex, reorder } from '../lib/protocol'
import { useApp } from '../store'
import { PlanOp, PlanResponse } from '../types'

type Draft = { [day: string]: { name: string; sets: string; reps: string; weight: string; note: string }[] }

// 计划编辑器：操作先在本地草稿上可视化，保存时统一走 ChangeProposal 协议
// （POST /plan/edits，带 base_version 乐观锁；422 时提示冲突并重新加载）。
export default function PlanEditor() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [draft, setDraft] = useState<Draft>({})
  const [ops, setOps] = useState<PlanOp[]>([])
  const [reason, setReason] = useState('')
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)
  const [saving, setSaving] = useState(false)
  const [picker, setPicker] = useState<{ day: string; replaceIndex?: number } | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [newName, setNewName] = useState('')

  const load = useCallback(() => {
    api.plan(uid).then((p) => {
      setPlan(p)
      const d: Draft = {}
      for (const day of p.content.schedule) {
        d[day.day] = day.exercises.map((ex) => ({
          name: ex.name, sets: String(ex.sets), reps: String(ex.reps),
          weight: ex.weight_kg != null ? String(ex.weight_kg) : '',
          note: ex.note || '',
        }))
      }
      setDraft(d)
      setOps([])
    }).catch((e) => setError({ message: e.message }))
  }, [uid])

  useEffect(() => { load() }, [load])

  if (error && !plan) return <div className="pt-4"><ErrorBox message={error.message} details={error.details} /></div>
  if (!plan) return <Spinner />

  const days = plan.content.schedule.map((d) => d.day)

  const mutate = (day: string, idx: number, patch: Partial<Draft[string][number]>) =>
    setDraft((d) => ({
      ...d,
      [day]: d[day].map((row, i) => (i === idx ? { ...row, ...patch } : row)),
    }))

  const pushOp = (op: PlanOp) => setOps((o) => [...o, op])

  const onAdd = (day: string, ex: { id: string; name: string }) => {
    setDraft((d) => ({ ...d, [day]: [...d[day], { name: ex.name, sets: '3', reps: '10', weight: '', note: '' }] }))
    pushOp(addExercise(day, ex.id || ex.name, 3, '10'))
  }

  const onReplace = (day: string, idx: number, ex: { id: string; name: string }) => {
    setDraft((d) => ({ ...d, [day]: d[day].map((row, i) => (i === idx ? { ...row, name: ex.name } : row)) }))
    pushOp(replaceByIndex(day, idx, ex.id || ex.name))
  }

  const commitEdits = (day: string, idx: number) => {
    const original = plan.content.schedule.find((x) => x.day === day)?.exercises[idx]
    if (!original) return
    const row = draft[day][idx]
    const patch: Parameters<typeof editPrescription>[2] = {}
    if (String(original.sets) !== row.sets) patch.sets = row.sets
    if (String(original.reps) !== row.reps) patch.reps = row.reps
    if ((original.weight_kg != null ? String(original.weight_kg) : '') !== row.weight)
      patch.weight_kg = row.weight === '' ? undefined : Number(row.weight)
    if ((original.note || '') !== row.note) patch.note = row.note
    if (Object.keys(patch).length) pushOp(editPrescription(day, idx, patch))
  }

  const save = async () => {
    if (!ops.length) { setError({ message: '没有待保存的修改' }); return }
    setSaving(true)
    setError(null)
    try {
      // P0-1：携带加载时的 base_version——并发修改会被后端 422 拒绝而非静默覆盖
      const result = await api.planEdits(uid, ops, reason || '手动编辑计划', plan.base_version)
      navigate('/training', { state: { saved: result.plan_version } })
    } catch (e) {
      const err = e as ApiError
      if (err.status === 422) {
        setError({ message: `${err.message}（页面已刷新到最新计划，请重做未保存的修改）`, details: err.details })
        load()
      } else {
        setError({ message: err.message, details: err.details })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="编辑计划"
        sub={`基于 v${plan.version} · ${ops.length} 项待保存修改`} />

      {error && <ErrorBox message={error.message} details={error.details} />}

      {days.map((day) => (
        <div key={day} className="card">
          {renaming === day ? (
            <div className="mb-2 flex gap-2">
              <input className="input" value={newName} autoFocus
                     onChange={(e) => setNewName(e.target.value)} placeholder="新训练日名" />
              <button className="btn-primary shrink-0"
                      onClick={() => {
                        if (newName.trim() && newName !== day) {
                          setDraft((d) => {
                            const nd = { ...d, [newName.trim()]: d[day] }
                            delete nd[day]
                            return nd
                          })
                          pushOp(renameDay(day, newName.trim()))
                        }
                        setRenaming(null)
                      }}>确定</button>
            </div>
          ) : (
            <div className="mb-2 flex items-center justify-between">
              <h3 className="font-semibold">{day}</h3>
              <div className="flex gap-2 text-xs">
                <button className="text-neutral-400 underline"
                        onClick={() => { setRenaming(day); setNewName(day) }}>改名</button>
                <button className="text-accent underline"
                        onClick={() => setPicker({ day })}>+ 加动作</button>
              </div>
            </div>
          )}
          <ul className="space-y-2">
            {(draft[day] || []).map((row, idx) => (
              <li key={idx} className="rounded-xl bg-neutral-800/60 p-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{row.name}</span>
                  <div className="flex gap-2 text-xs text-neutral-400">
                    <button disabled={idx === 0}
                            onClick={() => {
                              const list = draft[day]
                              const moved = [...list]
                              ;[moved[idx - 1], moved[idx]] = [moved[idx], moved[idx - 1]]
                              setDraft((d) => ({ ...d, [day]: moved }))
                              pushOp(reorder(day, idx, idx - 1))
                            }}>↑</button>
                    <button disabled={idx === draft[day].length - 1}
                            onClick={() => {
                              const list = draft[day]
                              const moved = [...list]
                              ;[moved[idx + 1], moved[idx]] = [moved[idx], moved[idx + 1]]
                              setDraft((d) => ({ ...d, [day]: moved }))
                              pushOp(reorder(day, idx, idx + 1))
                            }}>↓</button>
                    <button className="text-sky-400 underline"
                            onClick={() => setPicker({ day, replaceIndex: idx })}>替换</button>
                    <button className="text-red-400 underline"
                            onClick={() => {
                              setDraft((d) => ({ ...d, [day]: d[day].filter((_, i) => i !== idx) }))
                              pushOp(removeByIndex(day, idx))
                            }}>删除</button>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-1.5">
                  <input className="input !px-2 text-xs" value={row.sets} placeholder="组数"
                         onChange={(e) => mutate(day, idx, { sets: e.target.value })}
                         onBlur={() => commitEdits(day, idx)} />
                  <input className="input !px-2 text-xs" value={row.reps} placeholder="次数"
                         onChange={(e) => mutate(day, idx, { reps: e.target.value })}
                         onBlur={() => commitEdits(day, idx)} />
                  <input className="input !px-2 text-xs" value={row.weight} placeholder="kg"
                         inputMode="decimal"
                         onChange={(e) => mutate(day, idx, { weight: e.target.value })}
                         onBlur={() => commitEdits(day, idx)} />
                </div>
                <input className="input mt-1.5 !px-2 text-xs" value={row.note} placeholder="备注"
                       onChange={(e) => mutate(day, idx, { note: e.target.value })}
                       onBlur={() => commitEdits(day, idx)} />
              </li>
            ))}
          </ul>
        </div>
      ))}

      <div className="card">
        <label className="label">修改原因（会记录进版本历史）</label>
        <input className="input" value={reason} placeholder="例如：膝盖不适，换掉深蹲"
               onChange={(e) => setReason(e.target.value)} />
        <button className="btn-primary mt-3 w-full" disabled={saving || !ops.length}
                onClick={save}>
          {saving ? '保存中…' : `保存 ${ops.length} 项修改`}
        </button>
        <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
          修改走统一安全校验：隔离/医疗暂停期会拒绝保存；伤病部位的高压力动作会被拒绝加入。
          若提示版本冲突，说明计划刚被其他端修改过，已自动刷新。
        </p>
      </div>

      {picker && (
        <ExercisePicker
          onClose={() => setPicker(null)}
          onPick={(ex) => picker.replaceIndex !== undefined
            ? onReplace(picker.day, picker.replaceIndex, ex)
            : onAdd(picker.day, ex)}
        />
      )}
    </div>
  )
}
