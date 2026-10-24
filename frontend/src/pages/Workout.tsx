import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import ExercisePicker from '../components/ExercisePicker'
import { enqueueCheckin, newSubmissionId, queuedCount } from '../offline'
import { SessionEntry, useApp } from '../store'

export default function Workout() {
  const { day } = useParams()
  const uid = useApp((s) => s.uid)
  const session = useApp((s) => s.session)
  const { startSession, logSet, removeLastSet, replaceExercise, setSessionNotes,
          clearSession, startRest, restEndsAt, settings } = useApp((s) => s)
  const [error, setError] = useState('')
  const [pickerIdx, setPickerIdx] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<{ message: string; details?: string[] } | null>(null)
  const [now, setNow] = useState(Date.now())
  const navigate = useNavigate()
  const offlineSaved = useRef(false)

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!day) return
    // 已有当天的进行中会话直接恢复（刷新不丢）
    if (session && session.day === decodeURIComponent(day)) return
    const loadPlan = () => api.plan(uid).then((p) => { api.cachePlan(uid, p); return p })
      .catch((e) => {
        // 断网降级：最近一次加载的计划（隔离标记一并沿用缓存值）
        const cached = api.cachedPlan(uid)
        if ((e as { status?: number }).status === 0 && cached) return cached
        throw e
      })
    loadPlan().then((p) => {
      // P1-1：隔离中的旧处方不得作为可执行训练
      if (p.fenced) {
        setError('该计划已隔离（伤病/安全记录未解除）：旧动作安排暂不能执行。'
                 + '请先到「AI 教练」确认安全记录并共同确认重排。')
        return
      }
      const planDay = p.content.schedule.find((d) => d.day === decodeURIComponent(day))
      if (!planDay) { setError('计划里没有这一天'); return }
      // 上次重量是辅助信息:断网降级为空(不阻塞训练执行)
      return api.exerciseStates(uid).catch(() => ({ states: [] })).then((states) => {
        const last = new Map(states.states.map((s) => [s.exercise_id, s.last_weight]))
        startSession(decodeURIComponent(day), planDay.exercises.map((ex) => ({
          exercise_id: ex.exercise_id,
          name: ex.name,
          target: { sets: ex.sets, reps: ex.reps, weight: last.get(ex.exercise_id) ?? ex.weight_kg ?? null },
          note: ex.note,
          logged: [],
        })))
      })
    }).catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, uid])

  const entries = session?.day === decodeURIComponent(day || '') ? session.entries : null
  const restLeft = useMemo(() =>
    restEndsAt ? Math.max(0, Math.ceil((restEndsAt - now) / 1000)) : 0, [restEndsAt, now])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  // 保存成功后会清空会话：成功页与空会话守卫必须先于使用 entries 的计算
  if (saved) {
    return (
      <div className="space-y-4 pt-10 text-center">
        <p className="text-4xl">🎉</p>
        <p className="text-lg font-semibold">{saved}</p>
        <button className="btn-primary w-full" onClick={() => navigate('/history')}>查看训练历史</button>
        <button className="btn-ghost w-full" onClick={() => navigate('/today')}>回今日</button>
      </div>
    )
  }
  if (!entries) return <Spinner />

  const totalSets = entries.reduce((n, e) => n + e.logged.filter((l) => !l.warmup).length, 0)
  const volume = entries.reduce((n, e) =>
    n + e.logged.filter((l) => !l.warmup)
      .reduce((m, l) => m + (l.weight || 0) * (l.reps || 0), 0), 0)

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    const submissionId = newSubmissionId() // 稳定提交 ID：断网重试不重复入库
    const lines: string[] = []
    const exercises = entries.flatMap((e: SessionEntry) => {
      const done = e.logged.filter((l) => !l.warmup)
      if (!done.length) return []
      const name = e.replaced_with || e.name
      lines.push(`${name} ${done.length} 组：` + done.map((l) =>
        `${l.weight ?? '?'}kg×${l.reps ?? '?'}`).join('、'))
      // P0-4：每组完整保存（重量/次数/RPE/热身/完成时间）；聚合字段由服务端派生
      return [{ name, set_logs: e.logged.map((l) => ({
        weight_kg: l.weight, reps: l.reps, rpe: l.rpe, warmup: l.warmup, at: l.at,
      })) }]
    })
    if (!exercises.length) { setSaveError({ message: '还没有记录任何正式组' }); setSaving(false); return }
    const data = {
      exercises,
      raw: `${session!.day}：${lines.join('；')}${session!.notes ? `。备注：${session!.notes}` : ''}`,
    }
    try {
      const result = await api.saveCheckin(uid, 'training', data, submissionId)
      const warn = result.warnings.length ? `（${result.warnings.join('；')}）` : ''
      clearSession()
      setSaved(`已保存 ${exercises.length} 个动作、${totalSets} 组${warn}`)
      offlineSaved.current = false
    } catch (e) {
      const err = e as ApiError
      if (err.status === 0) {
        await enqueueCheckin(uid, 'training', data, submissionId)
        useApp.getState().setOfflineCount(await queuedCount())
        clearSession()
        setSaved('当前离线：训练已暂存到本机，恢复网络后自动同步。')
        offlineSaved.current = true
      } else {
        setSaveError({ message: err.message, details: err.details })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`space-y-3 pt-4 ${restLeft > 0 ? 'pb-28' : ''}`}>
      <PageHeader title={session!.day} sub={`训练日 · 已完成 ${totalSets} 组 · 计量 ${Math.round(volume)} kg`} />

      {saveError && <ErrorBox message={saveError.message} details={saveError.details} />}

      {entries.map((e, idx) => {
        const isWarmupOnly = e.logged.length > 0 && e.logged.every((l) => l.warmup)
        return (
          <div key={idx} className="card">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">{e.replaced_with || e.name}</h3>
                <p className="text-xs text-neutral-500">
                  目标 {e.target.sets}×{e.target.reps}
                  {e.target.weight != null ? ` · 上次 ${e.target.weight}kg` : ''}
                  {e.note ? ` · ${e.note}` : ''}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {isWarmupOnly && <Tag tone="amber">仅热身</Tag>}
                <button className="text-xs text-neutral-400 underline"
                        onClick={() => setPickerIdx(idx)}>替换</button>
              </div>
            </div>

            {e.logged.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {e.logged.map((l, i) => (
                  <span key={i} className={`tag ${l.warmup ? 'bg-amber-900/50 text-amber-300' : 'bg-neutral-800 text-neutral-300'}`}>
                    {l.warmup ? '热身 ' : ''}{l.weight ?? '?'}kg×{l.reps ?? '?'}{l.rpe ? ` RPE${l.rpe}` : ''}
                  </span>
                ))}
                <button className="tag text-neutral-500 underline"
                        onClick={() => removeLastSet(idx)}>撤销</button>
              </div>
            )}

            <SetForm onDone={(s) => { logSet(idx, s); if (!s.warmup) startRest() }} />
          </div>
        )
      })}

      <div className="card">
        <label className="label">训练感受 / 备注</label>
        <textarea className="input min-h-16" value={session!.notes}
                  onChange={(ev) => setSessionNotes(ev.target.value)}
                  placeholder="例如：深蹲膝盖有点紧，重量保守" />
      </div>

      <button className="btn-primary w-full" disabled={saving || totalSets === 0} onClick={save}>
        {saving ? '保存中…' : `完成训练（${totalSets} 组）`}
      </button>
      <p className="text-center text-[11px] text-neutral-600">
        断网时记录会暂存本机（IndexedDB），恢复网络自动同步，不会丢失。
      </p>

      {restLeft > 0 && (
        <div className="fixed inset-x-0 bottom-16 z-40 mx-auto flex max-w-lg items-center justify-between
                        border-t border-neutral-800 bg-neutral-900 px-4 py-3">
          <span className="text-sm text-neutral-300">休息 {restLeft}s</span>
          <button className="btn-ghost !py-1.5 text-xs" onClick={() => useApp.getState().stopRest()}>
            跳过（默认 {settings.restSeconds}s）
          </button>
        </div>
      )}

      {pickerIdx !== null && (
        <ExercisePicker
          onClose={() => setPickerIdx(null)}
          onPick={(ex) => replaceExercise(pickerIdx, ex.name)}
        />
      )}
    </div>
  )
}

function SetForm({ onDone }: { onDone: (s: { weight: number | null; reps: number | null; rpe: number | null; warmup: boolean; at?: string }) => void }) {
  const [weight, setWeight] = useState('')
  const [reps, setReps] = useState('')
  const [rpe, setRpe] = useState('')
  const [warmup, setWarmup] = useState(false)
  return (
    <div className="mt-2.5 flex items-center gap-1.5">
      <input className="input !px-2 text-center text-sm" placeholder="kg" inputMode="decimal"
             value={weight} onChange={(e) => setWeight(e.target.value)} />
      <input className="input !px-2 text-center text-sm" placeholder="次" inputMode="numeric"
             value={reps} onChange={(e) => setReps(e.target.value)} />
      <input className="input !px-2 text-center text-sm" placeholder="RPE" inputMode="decimal"
             value={rpe} onChange={(e) => setRpe(e.target.value)} />
      <button className={`shrink-0 rounded-lg px-2 py-2 text-xs ${warmup ? 'bg-amber-800 text-amber-200' : 'bg-neutral-800 text-neutral-400'}`}
              onClick={() => setWarmup((w) => !w)}>热身</button>
      <button className="btn-primary shrink-0 !px-3"
              onClick={() => {
                onDone({
                  weight: weight === '' ? null : Number(weight),
                  reps: reps === '' ? null : Number(reps),
                  rpe: rpe === '' ? null : Number(rpe),
                  warmup,
                  at: new Date().toISOString(),
                })
                setWeight(''); setReps(''); setRpe(''); setWarmup(false)
              }}>✓</button>
    </div>
  )
}
