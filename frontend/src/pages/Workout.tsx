import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  BookOpen, Check, ChevronDown, ChevronUp, Plus, Repeat2, Timer,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { Button, ErrorBox, Sheet, Spinner, SuccessBlock } from '../components/Bits'
import ExercisePicker from '../components/ExercisePicker'
import { enqueueCheckin, newSubmissionId, queuedCount } from '../offline'
import { parseTrainingNumber, validateSetValues } from '../lib/validate'
import { SessionEntry, useApp } from '../store'

export default function Workout() {
  const { day } = useParams()
  const uid = useApp((s) => s.uid)
  const session = useApp((s) => s.session)
  const { startSession, startFreeSession, addFreeExercise, removeEntry, replaceExercise,
          setSessionNotes, clearSession, restEndsAt, settings } = useApp((s) => s)
  const [error, setError] = useState('')
  const [pickerIdx, setPickerIdx] = useState<number | null>(null)
  const [addingFree, setAddingFree] = useState(false)
  // P0-1：会话切换提示（store 保留现有会话后，由用户明确选择恢复或放弃）
  const [switchPrompt, setSwitchPrompt] = useState<{
    activeLabel: string; activeHref: string; begin: () => void
  } | null>(null)
  const switchBeginRef = useRef<(() => void) | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<{ message: string; details?: string[] } | null>(null)
  const [now, setNow] = useState(Date.now())
  const navigate = useNavigate()
  const offlineSaved = useRef(false)
  const isFree = day === 'free'

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!day) return
    // M6.3 自由训练：不依赖计划，进入即建空会话，动作随加随练
    if (isFree) {
      if (session && session.mode === 'free') return
      const r = startFreeSession()
      if (r.resumed) return                      // 同目标恢复：现有会话原样继续
      if (r.kept) {
        const cur = useApp.getState().session!
        const n = cur.entries.reduce((s, e) => s + e.logged.filter((l) => !l.warmup).length, 0)
        switchBeginRef.current = () => startFreeSession()
        setSwitchPrompt({
          activeLabel: `自由训练（已记录 ${n} 组）`, activeHref: '/workout/free',
          begin: () => startFreeSession(),
        })
      }
      return
    }
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
        const plannedEntries = planDay.exercises.map((ex) => ({
          exercise_id: ex.exercise_id,
          name: ex.name,
          target: { sets: ex.sets, reps: ex.reps, weight: last.get(ex.exercise_id) ?? ex.weight_kg ?? null },
          note: ex.note,
          logged: [],
        }))
        const r = startSession(decodeURIComponent(day), plannedEntries)
        if (r.resumed) return                      // 同目标恢复：现有会话原样继续
        if (r.kept) {
          const cur = useApp.getState().session!
          const n = cur.entries.reduce((s, e) => s + e.logged.filter((l) => !l.warmup).length, 0)
          const begin = () => startSession(decodeURIComponent(day), plannedEntries)
          switchBeginRef.current = begin
          setSwitchPrompt({
            activeLabel: `${cur.mode === 'free' ? '自由训练' : cur.day}（已记录 ${n} 组）`,
            activeHref: cur.mode === 'free' ? '/workout/free' : `/workout/${encodeURIComponent(cur.day)}`,
            begin,
          })
        }
      })
    }).catch((e) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [day, uid])

  const entries = session?.day === decodeURIComponent(day || '') ? session.entries : null
  const restLeft = useMemo(() =>
    restEndsAt ? Math.max(0, Math.ceil((restEndsAt - now) / 1000)) : 0, [restEndsAt, now])
  const restTotal = settings.restSeconds

  if (error) {
    return (
      <div className="mx-auto min-h-dvh w-full max-w-xl px-4 pt-6">
        <button className="btn-plain mb-3" onClick={() => navigate(-1)}>← 返回</button>
        <ErrorBox message={error} />
      </div>
    )
  }
  // 保存成功后会清空会话：成功页与空会话守卫必须先于使用 entries 的计算
  if (saved) {
    return (
      <div className="mx-auto min-h-dvh w-full max-w-xl px-4 pb-10 pt-16">
        <SuccessBlock title="训练已保存">
          <p className="max-w-72 text-sm leading-relaxed text-muted">{saved}</p>
        </SuccessBlock>
        <div className="space-y-3">
          <Button block onClick={() => navigate(offlineSaved.current ? '/today' : '/history')}>
            {offlineSaved.current ? '回今日' : '查看训练历史'}
          </Button>
          <Button block variant="ghost" onClick={() => navigate(offlineSaved.current ? '/history' : '/today')}>
            {offlineSaved.current ? '查看今日' : '回今日'}
          </Button>
        </div>
      </div>
    )
  }
  // P0-1：会话切换需用户明确选择，绝不静默覆盖（在会话未就绪时也要可见）
  if (switchPrompt) {
    return (
      <div className="mx-auto min-h-dvh w-full max-w-xl px-4">
        <Sheet open
               onClose={() => { setSwitchPrompt(null); navigate(switchPrompt.activeHref) }}
               title="有一个进行中的训练">
          <p className="text-sm leading-relaxed text-muted">
            你有一个未完成的训练：<b className="text-ink">{switchPrompt.activeLabel}</b>。
            已为你保留，不会因为开始新训练而丢失。
          </p>
          <div className="mt-4 space-y-2.5">
            <Button block onClick={() => { setSwitchPrompt(null); navigate(switchPrompt.activeHref) }}>
              回到进行中的训练
            </Button>
            <Button block variant="danger"
                    onClick={() => {
                      clearSession()
                      switchBeginRef.current?.()
                      setSwitchPrompt(null)
                    }}>
              放弃已记录的组，开始新的
            </Button>
          </div>
        </Sheet>
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
      // M6.3：随记录提交稳定动作 ID（临时替换用替换后的 ID；断言由服务端校验）
      const exerciseId = (e.replaced_with ? e.replace_exercise_id : e.exercise_id) || undefined
      // P0-4：每组完整保存（重量/次数/RPE/热身/完成时间）；聚合字段由服务端派生
      return [{ name, exercise_id: exerciseId, set_logs: e.logged.map((l) => ({
        weight_kg: l.weight, reps: l.reps, rpe: l.rpe, warmup: l.warmup, at: l.at,
      })) }]
    })
    if (!exercises.length) { setSaveError({ message: '还没有记录任何正式组' }); setSaving(false); return }
    const label = session!.mode === 'free' ? `自由训练 ${session!.date}` : session!.day
    const data = {
      exercises,
      raw: `${label}：${lines.join('；')}${session!.notes ? `。备注：${session!.notes}` : ''}`,
      // M6.3.1：会话元数据随记录入库（自由/计划执行比例、真实时长、时区口径的基础）
      session_meta: {
        session_id: session!.id,
        mode: session!.mode,
        started_at: session!.started_at,
        completed_at: new Date().toISOString(),
        local_date: session!.date,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
      },
    }
    try {
      const result = await api.saveCheckin(uid, 'training', data, submissionId)
      const warn = result.warnings.length ? `（${result.warnings.join('；')}）` : ''
      clearSession()
      setSaved(`共 ${exercises.length} 个动作、${totalSets} 组${warn}`)
      offlineSaved.current = false
    } catch (e) {
      const err = e as ApiError
      if (err.status === 0) {
        await enqueueCheckin(uid, 'training', data, submissionId)
        useApp.getState().setOfflineCount(await queuedCount())
        clearSession()
        setSaved('当前离线：训练已暂存到本机，恢复网络后自动同步，不会丢失。')
        offlineSaved.current = true
      } else {
        setSaveError({ message: err.message, details: err.details })
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-dvh bg-canvas">
      {/* 沉浸式顶栏（深色，含进度） */}
      <header className="sticky top-0 z-30 bg-night text-white"
              style={{ paddingTop: 'env(safe-area-inset-top)' }}>
        <div className="mx-auto flex w-full max-w-xl items-center gap-3 px-4 py-3">
          <button className="-ml-2 flex size-9 items-center justify-center rounded-full
                             text-white/80 transition-colors hover:bg-white/10"
                  onClick={() => navigate('/today')} aria-label="结束并返回今日">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[17px] font-bold leading-tight">
              {session!.mode === 'free' ? '自由训练' : session!.day}
            </h1>
            <p className="nums text-xs text-white/60">
              已完成 {totalSets} 组 · 计量 {Math.round(volume)} kg
              {session!.mode === 'free' && ' · 不影响计划'}
            </p>
          </div>
          {restLeft > 0 && (
            <span className="nums flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5
                             text-sm font-bold text-ink">
              <Timer size={15} /> {restLeft}s
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto w-full max-w-xl space-y-4 px-4 pb-52 pt-4">
        {saveError && <ErrorBox message={saveError.message} details={saveError.details} />}

        {/* 自由训练：空会话引导 */}
        {isFree && entries.length === 0 && (
          <div className="card flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-lg font-bold">自由训练</p>
            <p className="max-w-64 text-sm leading-relaxed text-muted">
              不按计划、想练什么就练什么。添加动作、逐组记录，完成后保存为历史——不影响当前计划。
            </p>
            <Button onClick={() => setAddingFree(true)}>
              <Plus size={16} /> 添加第一个动作
            </Button>
          </div>
        )}

        {entries.map((e, idx) => (
          <ExerciseBlock key={idx} idx={idx} entry={e} isFree={isFree}
                         onPickReplace={() => setPickerIdx(idx)}
                         onRemove={() => removeEntry(idx)} />
        ))}

        {isFree && entries.length > 0 && (
          <Button variant="ghost" block onClick={() => setAddingFree(true)}>
            <Plus size={16} /> 添加动作
          </Button>
        )}

        {/* 训练感受 */}
        <div className="card">
          <label className="label" htmlFor="session-notes">训练感受 / 备注</label>
          <textarea id="session-notes" className="input min-h-20"
                    value={session!.notes}
                    onChange={(ev) => setSessionNotes(ev.target.value)}
                    placeholder="例如：深蹲膝盖有点紧，重量保守" />
        </div>

        <p className="text-center text-xs leading-relaxed text-muted">
          断网时记录会暂存本机（IndexedDB），恢复网络自动同步，不会丢失。
        </p>
      </main>

      {/* 固定底部：休息计时器 + 完成训练入口 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-surface/95 backdrop-blur"
           style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <div className="mx-auto w-full max-w-xl space-y-2.5 px-4 pb-3 pt-3">
          {restLeft > 0 && (
            <div className="flex items-center gap-3 rounded-2xl bg-night px-4 py-3 text-white">
              <Timer size={18} className="shrink-0 text-accent" />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium">休息中</span>
                  <span className="nums text-lg font-bold text-accent">{restLeft}s</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/15">
                  <div className="h-full rounded-full bg-accent transition-[width] duration-1000 ease-linear"
                       style={{ width: `${(restLeft / restTotal) * 100}%` }} />
                </div>
              </div>
              <button className="btn-sm btn shrink-0 bg-white/10 text-white hover:bg-white/20"
                      onClick={() => useApp.getState().stopRest()}>
                跳过
              </button>
            </div>
          )}
          <button className="btn-primary w-full text-base" disabled={saving || totalSets === 0} onClick={save}>
            {saving ? '保存中…' : `完成训练（${totalSets} 组）`}
          </button>
        </div>
      </div>

      {pickerIdx !== null && (
        <ExercisePicker
          onClose={() => setPickerIdx(null)}
          onPick={(ex) => replaceExercise(pickerIdx, ex.name, ex.id)}
        />
      )}
      {addingFree && (
        <ExercisePicker
          onClose={() => setAddingFree(false)}
          onPick={(ex) => addFreeExercise({
            exercise_id: ex.id, name: ex.name,
            target: { sets: '—', reps: '—', weight: null }, logged: [],
          })}
        />
      )}
    </div>
  )
}

/** 单个动作卡：大标题 + 教学入口 + 组记录表 + 快速输入 */
function ExerciseBlock({ idx, entry, isFree, onPickReplace, onRemove }: {
  idx: number; entry: SessionEntry; isFree: boolean
  onPickReplace: () => void; onRemove: () => void
}) {
  const logSet = useApp((s) => s.logSet)
  const removeLastSet = useApp((s) => s.removeLastSet)
  const startRest = useApp((s) => s.startRest)
  const [rpeOpen, setRpeOpen] = useState(false)
  const done = entry.logged.filter((l) => !l.warmup).length
  const targetSets = Number(entry.target.sets) || 0
  const targetReps = entry.target.reps !== '—' ? entry.target.reps : null
  const isWarmupOnly = entry.logged.length > 0 && entry.logged.every((l) => l.warmup)
  const prevWeight = entry.target.weight
  const displayName = entry.replaced_with || entry.name
  const teachId = entry.replaced_with ? entry.replace_exercise_id : entry.exercise_id

  return (
    <div className="card !p-0 overflow-hidden">
      {/* 动作头 */}
      <div className="flex items-start justify-between gap-3 px-4 pb-3 pt-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="nums flex size-6 shrink-0 items-center justify-center rounded-full
                             bg-ink/6 text-xs font-bold text-muted">{idx + 1}</span>
            <h2 className="truncate text-xl font-bold leading-tight">{displayName}</h2>
          </div>
          <p className="nums mt-1.5 text-[13px] text-muted">
            {targetSets > 0 && `目标 ${targetSets}×${targetReps ?? '—'}`}
            {targetSets > 0 && prevWeight != null && ` · 上次 ${prevWeight}kg`}
            {entry.note && ` · ${entry.note}`}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {teachId && (
            <Link to={`/explore/${encodeURIComponent(teachId)}`}
                  className="btn-plain" aria-label={`查看 ${displayName} 教学`}>
              <BookOpen size={15} /> 教学
            </Link>
          )}
          <button className="btn-plain" onClick={onPickReplace}>
            <Repeat2 size={15} /> 替换
          </button>
          {isFree && (
            <button className="btn-plain !text-red-500" onClick={onRemove} aria-label="移除动作">
              移除
            </button>
          )}
        </div>
      </div>

      {/* 已记录组 */}
      {entry.logged.length > 0 && (
        <div className="mx-4 mb-3 overflow-hidden rounded-xl border border-line">
          {entry.logged.map((l, i) => (
            <div key={i}
                 className={`nums flex items-center gap-2 px-3 py-2 text-sm ${
                   i % 2 === 0 ? 'bg-surface' : 'bg-canvas'}`}>
              <span className={`flex size-5 items-center justify-center rounded-full text-2xs font-bold ${
                l.warmup ? 'bg-amber-100 text-amber-700' : 'bg-accent-soft text-accent-deep'}`}>
                {i + 1}
              </span>
              {l.warmup && <span className="tag bg-amber-50 text-amber-700">热身</span>}
              <span className="ml-auto font-medium">
                {l.weight ?? '?'} <span className="text-xs text-muted">kg</span>
                <span className="mx-1 text-muted">×</span>
                {l.reps ?? '?'} <span className="text-xs text-muted">次</span>
              </span>
              {l.rpe != null && <span className="text-xs text-muted">RPE {l.rpe}</span>}
              <Check size={14} className="text-accent-deep" />
            </div>
          ))}
        </div>
      )}
      {isWarmupOnly && (
        <p className="mx-4 mb-2 text-xs text-amber-700">仅记录了热身组，尚无正式组。</p>
      )}
      {done > 0 && done < targetSets && (
        <p className="mx-4 mb-2 text-xs text-muted">
          已完成 {done}/{targetSets} 组，还差 {targetSets - done} 组。
        </p>
      )}

      <SetForm onDone={(s) => { logSet(idx, s); if (!s.warmup) startRest() }}
               onUndo={() => removeLastSet(idx)}
               canUndo={entry.logged.length > 0}
               rpeOpen={rpeOpen} setRpeOpen={setRpeOpen}
               suggestWeight={prevWeight} suggestReps={Number(entry.target.reps) || undefined} />
    </div>
  )
}

/** 逐组快速输入：重量/次数大输入区 + 热身区分 + 快捷步进 + 可展开 RPE；正式组次数必填 */
function SetForm({ onDone, onUndo, canUndo, rpeOpen, setRpeOpen, suggestWeight, suggestReps }: {
  onDone: (s: { weight: number | null; reps: number | null; rpe: number | null; warmup: boolean; at?: string }) => void
  onUndo: () => void; canUndo: boolean
  rpeOpen: boolean; setRpeOpen: (v: boolean) => void
  suggestWeight?: number | null; suggestReps?: number
}) {
  const [weight, setWeight] = useState(suggestWeight != null ? String(suggestWeight) : '')
  const [reps, setReps] = useState(suggestReps ? String(suggestReps) : '')
  const [rpe, setRpe] = useState('')
  const [warmup, setWarmup] = useState(false)
  const [formError, setFormError] = useState('')

  const submit = () => {
    // M6.1.1：范围校验与历史纠错共用 lib/validate 同一套规则
    const w = parseTrainingNumber(weight)
    const r = parseTrainingNumber(reps)
    const p = parseTrainingNumber(rpe)
    if (w === undefined || r === undefined || p === undefined) {
      setFormError('重量 / 次数 / RPE 需为有效数字'); return
    }
    const invalid = validateSetValues(w, r, p, warmup)
    if (invalid) { setFormError(invalid); return }
    setFormError('')
    // 连续记录：重量与次数保留（多为组间不变），RPE/热身复位
    onDone({ weight: w, reps: r, rpe: p, warmup, at: new Date().toISOString() })
    setRpe(''); setWarmup(false)
  }

  // 快捷步进：空值时 + 步进从合理起点开始，负向不允许低于最小值
  const stepWeight = (d: number) => {
    setFormError('')
    const cur = parseTrainingNumber(weight)
    const base = typeof cur === 'number' ? cur : 0
    const next = Math.round((base + d) * 100) / 100
    if (next <= 0) return
    setWeight(String(next))
  }
  const stepReps = (d: number) => {
    setFormError('')
    const cur = parseTrainingNumber(reps)
    const base = typeof cur === 'number' ? Math.floor(cur) : 0
    const next = base + d
    if (next < 1) return
    setReps(String(next))
  }

  const stepBtn = 'flex h-9 flex-1 items-center justify-center rounded-lg border border-line ' +
    'bg-surface text-xs font-medium text-muted transition-colors hover:border-lineStrong hover:text-ink ' +
    'disabled:opacity-40'

  return (
    <div className="border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      <div className="flex items-center gap-2">
        <button
          className={`tag h-11 shrink-0 px-3 transition-colors ${
            warmup ? 'bg-amber-400 text-amber-950' : 'border border-line bg-surface text-muted'}`}
          onClick={() => { setWarmup((w) => !w); setFormError('') }}
          aria-pressed={warmup}>
          热身
        </button>
        <div className="relative flex-1">
          <input className="input nums h-12 rounded-xl text-center text-lg font-semibold" placeholder="重量"
                 inputMode="decimal" value={weight}
                 onChange={(e) => { setWeight(e.target.value); setFormError('') }} />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">kg</span>
        </div>
        <div className="relative flex-1">
          <input className="input nums h-12 rounded-xl text-center text-lg font-semibold" placeholder="次数"
                 inputMode="numeric" value={reps}
                 onChange={(e) => { setReps(e.target.value); setFormError('') }} />
          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">次</span>
        </div>
        <button className={`flex size-11 shrink-0 items-center justify-center rounded-xl border transition-colors ${
          rpeOpen ? 'border-accent-deep/40 bg-accent-soft text-accent-deep'
                  : 'border-line bg-surface text-muted'}`}
                onClick={() => setRpeOpen(!rpeOpen)}
                aria-expanded={rpeOpen} aria-label="展开 RPE">
          {rpeOpen ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
        </button>
      </div>

      {/* 快捷步进：免键盘调整 */}
      <div className="mt-2 flex items-center gap-2">
        <div className="flex flex-1 items-center gap-1.5">
          <button className={stepBtn} onClick={() => stepWeight(-2.5)} disabled={!weight}
                  aria-label="重量减 2.5 公斤">−2.5</button>
          <button className={stepBtn} onClick={() => stepWeight(2.5)} aria-label="重量加 2.5 公斤">+2.5</button>
        </div>
        <div className="flex flex-1 items-center gap-1.5">
          <button className={stepBtn} onClick={() => stepReps(-1)} disabled={!reps}
                  aria-label="次数减 1">−1</button>
          <button className={stepBtn} onClick={() => stepReps(1)} aria-label="次数加 1">+1</button>
        </div>
      </div>

      {rpeOpen && (
        <div className="mt-2 animate-fade-up">
          <input className="input nums input-sm text-center" placeholder="RPE（可选，1-10）"
                 inputMode="decimal" value={rpe}
                 onChange={(e) => { setRpe(e.target.value); setFormError('') }} />
        </div>
      )}

      {formError && (
        <p className="mt-2 text-center text-xs font-medium text-red-600" role="alert">{formError}</p>
      )}

      <div className="mt-2.5 flex gap-2">
        <button className="btn-plain shrink-0" disabled={!canUndo} onClick={onUndo}>
          撤销上一组
        </button>
        <button className="btn-primary flex-1" onClick={submit}>
          <Check size={17} strokeWidth={2.5} /> 完成本组
        </button>
      </div>
    </div>
  )
}
