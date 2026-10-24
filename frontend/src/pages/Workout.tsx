import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  BookMarked, BookOpen, Check, ChevronDown, ChevronUp, Plus, Repeat2, Timer,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { Button, ErrorBox, Sheet, Spinner, SuccessBlock } from '../components/Bits'
import ExercisePicker from '../components/ExercisePicker'
import { enqueueCheckin, newSubmissionId, queuedCount } from '../offline'
import { parseTrainingNumber, validateSetDraft } from '../lib/validate'
import { formatSetCompact, formatSetRecord } from '../lib/setDisplay'
import { LoggedSet, SessionEntry, useApp } from '../store'
import type { MeasurementType } from '../types'

export default function Workout() {
  const { day, templateId } = useParams()
  const uid = useApp((s) => s.uid)
  const session = useApp((s) => s.session)
  const { startSession, startFreeSession, addFreeExercise, removeEntry, replaceExercise,
          setSessionNotes, clearSession, restEndsAt, settings } = useApp((s) => s)
  const [error, setError] = useState('')
  const [pickerIdx, setPickerIdx] = useState<number | null>(null)
  const [addingFree, setAddingFree] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [templateName, setTemplateName] = useState('')
  const [templateNote, setTemplateNote] = useState('')
  const [templateSaved, setTemplateSaved] = useState('')
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
  const isFree = day === 'free' || !!templateId

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    if (!day && !templateId) return
    // M6.4-A 场景 A：从模板开始（自由会话预填动作，不影响计划与模板本身）
    if (templateId) {
      const tid = Number(templateId)
      // P0-2：模板会话身份一致才恢复——不同模板必须走切换保护，不能直接显示旧模板
      if (session && session.mode === 'free' && session.templateId === tid) return
      api.trainingTemplates(uid).then((r) => {
        const tpl = r.templates.find((t) => t.id === tid)
        if (!tpl) { setError('模板不存在或已删除'); return }
        const label = `模板 · ${tpl.name}`
        const rr = startFreeSession({ label, templateId: tid })
        if (rr.resumed) return        // 同模板会话恢复：已预填，直接继续
        if (rr.kept) {
          const cur = useApp.getState().session!
          const n = cur.entries.reduce((s, e) => s + e.logged.filter((l) => !l.warmup).length, 0)
          setSwitchPrompt({
            activeLabel: `${cur.day === 'free' ? '自由训练' : cur.day}（已记录 ${n} 组）`,
            activeHref: '/workout/free',
            begin: () => startFreeSession({ label, templateId: tid }),
          })
          return
        }
        for (const en of tpl.entries) {
          useApp.getState().addFreeExercise({
            exercise_id: en.exercise_id, name: en.name,
            measurement: en.measurement, supersetGroup: en.superset_group,
            target: { sets: '—', reps: '—', weight: null }, logged: [],
          })
        }
      }).catch((e) => setError(e.message))
      return
    }
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
    if (session && session.day === decodeURIComponent(day || "")) return
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
      const planDay = p.content.schedule.find((d) => d.day === decodeURIComponent(day || ""))
      if (!planDay) { setError('计划里没有这一天'); return }
      // 上次重量是辅助信息:断网降级为空(不阻塞训练执行)
      return Promise.all([
        api.exerciseStates(uid).catch(() => ({ states: [] })),
        api.exercises().catch(() => ({ exercises: [] })),
      ]).then(([statesRes, sums]) => {
        const last = new Map(statesRes.states.map((s) => [s.exercise_id, s.last_weight]))
        const typeMap = new Map(sums.exercises.map((x) => [x.id, x.measurement]))
        const plannedEntries = planDay.exercises.map((ex) => ({
          exercise_id: ex.exercise_id,
          name: ex.name,
          measurement: typeMap.get(ex.exercise_id) || 'weight_reps',
          target: { sets: ex.sets, reps: ex.reps, weight: last.get(ex.exercise_id) ?? ex.weight_kg ?? null },
          note: ex.note,
          logged: [],
        }))
        const r = startSession(decodeURIComponent(day || ""), plannedEntries,
                               { planId: p.plan_id, planVersion: p.version })
        if (r.resumed) return                      // 同目标恢复：现有会话原样继续
        if (r.kept) {
          const cur = useApp.getState().session!
          const n = cur.entries.reduce((s, e) => s + e.logged.filter((l) => !l.warmup).length, 0)
          const begin = () => startSession(decodeURIComponent(day || ""), plannedEntries)
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

  // 自由/模板会话（mode=free）在 /workout/free 或模板路由都可恢复；计划会话按日名匹配
  const entries = session
    ? (session.mode === 'free' || session.day === decodeURIComponent(day || '')
        ? session.entries : null)
    : null
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
      .reduce((m, l) => {
        if (l.type === undefined || l.type === 'weight_reps')
          return m + (l.weight_kg || 0) * (l.reps || 0)
        if (l.type === 'bodyweight_reps') return m + (l.added_weight_kg || 0) * (l.reps || 0)
        return m
      }, 0), 0)

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    const submissionId = newSubmissionId() // 稳定提交 ID：断网重试不重复入库
    const lines: string[] = []
    const exercises = entries.flatMap((e: SessionEntry) => {
      const done = e.logged.filter((l) => !l.warmup)
      if (!done.length) return []
      const name = e.replaced_with || e.name
      lines.push(`${name} ${done.length} 组：` + done.map(formatSetCompact).join('、'))
      // M6.3：随记录提交稳定动作 ID（临时替换用替换后的 ID；断言由服务端校验）
      const exerciseId = (e.replaced_with ? e.replace_exercise_id : e.exercise_id) || undefined
      // P0-4/M6.4-A：每组完整保存（类型化记录 + 热身/完成时间）；聚合字段由服务端派生
      return [{
        name, exercise_id: exerciseId,
        superset_group: e.supersetGroup || undefined,
        set_logs: e.logged.map((l) => ({
          type: l.type || 'weight_reps',
          weight_kg: l.type === 'weight_reps' ? l.weight_kg : undefined,
          added_weight_kg: l.type === 'bodyweight_reps' ? l.added_weight_kg : undefined,
          assistance_kg: l.type === 'assisted_reps' ? l.assistance_kg : undefined,
          reps: 'reps' in l ? l.reps : undefined,
          duration_seconds: 'duration_seconds' in l ? l.duration_seconds : undefined,
          distance_m: 'distance_m' in l ? l.distance_m : undefined,
          rpe: 'rpe' in l ? l.rpe : undefined,
          warmup: l.warmup, at: l.at,
        })),
      }]
    })
    if (!exercises.length) { setSaveError({ message: '还没有记录任何正式组' }); setSaving(false); return }
    const label = session!.mode === 'planned' ? session!.day
      : session!.day === 'free' ? `自由训练 ${session!.date}` : session!.day
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
        ...(session!.templateId ? { template_id: session!.templateId } : {}),
        ...(session!.planId ? { plan_id: session!.planId,
                                plan_version: session!.planVersion } : {}),
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
              {session!.mode === 'planned' ? session!.day
                : session!.day === 'free' ? '自由训练' : session!.day}
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
          <>
            <Button variant="ghost" block onClick={() => setAddingFree(true)}>
              <Plus size={16} /> 添加动作
            </Button>
            <Button variant="ghost" block
                    onClick={() => { setTemplateName(''); setTemplateNote(''); setTemplateSaved(''); setSavingTemplate(true) }}>
              <BookMarked size={16} /> 存为训练模板
            </Button>
          </>
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
            exercise_id: ex.id, name: ex.name, measurement: ex.measurement,
            target: { sets: '—', reps: '—', weight: null }, logged: [],
          })}
        />
      )}
      {/* M6.4-A 场景 A：把这次训练存为可复用模板 */}
      {savingTemplate && (
        <Sheet open onClose={() => setSavingTemplate(false)} title="存为训练模板">
          <p className="mb-3 rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
            模板记录动作、顺序、记录类型与超级组分组；修改模板不影响已保存的训练，也不会改动当前计划。
          </p>
          <label className="label" htmlFor="tpl-name">模板名称</label>
          <input id="tpl-name" className="input" placeholder="例如：胸背超级组日"
                 value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
          <label className="label mt-3" htmlFor="tpl-note">备注（可选）</label>
          <input id="tpl-note" className="input" placeholder="例如：交替完成，组间休息 60 秒"
                 value={templateNote} onChange={(e) => setTemplateNote(e.target.value)} />
          {templateSaved && (
            <p className="mt-3 rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
              {templateSaved}
            </p>
          )}
          <Button block className="mt-3"
                  disabled={!templateName.trim()}
                  onClick={async () => {
                    try {
                      await api.saveTrainingTemplate(uid, {
                        name: templateName.trim(),
                        note: templateNote.trim() || undefined,
                        entries: entries.map((e) => ({
                          exercise_id: (e.replaced_with ? e.replace_exercise_id : e.exercise_id) || '',
                          name: e.replaced_with || e.name,
                          measurement: e.measurement,
                          superset_group: e.supersetGroup,
                        })),
                      })
                      setSavingTemplate(false)
                      setTemplateSaved(`已保存模板「${templateName.trim()}」——训练页可随时开始`)
                    } catch (err) {
                      setSaveError({ message: (err as ApiError).message })
                      setSavingTemplate(false)
                    }
                  }}>
            保存模板（{entries.length} 个动作）
          </Button>
        </Sheet>
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
  const setEntryGroup = useApp((s) => s.setEntryGroup)
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
      {isFree && (
        <div className="flex items-center gap-1.5 px-4 pb-2.5" aria-label="超级组分组">
          <span className="text-2xs text-muted">超级组</span>
          {([null, 'A', 'B', 'C'] as const).map((g) => (
            <button key={g ?? 'none'} onClick={() => setEntryGroup(idx, g ?? undefined)}
                    className={`tag min-h-7 px-2 transition-colors ${
                      (entry.supersetGroup ?? null) === g
                        ? 'bg-night text-white'
                        : 'border border-line bg-surface text-muted'}`}>
              {g ?? '无'}
            </button>
          ))}
        </div>
      )}

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
              <span className="ml-auto font-medium">{formatSetRecord(l)}</span>
              {'rpe' in l && l.rpe != null && <span className="text-xs text-muted">RPE {l.rpe}</span>}
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

      <SetForm measurement={entry.measurement || 'weight_reps'}
               onDone={(s) => { logSet(idx, s); if (!s.warmup) startRest() }}
               onUndo={() => removeLastSet(idx)}
               canUndo={entry.logged.length > 0}
               rpeOpen={rpeOpen} setRpeOpen={setRpeOpen}
               suggestWeight={prevWeight} suggestReps={Number(entry.target.reps) || undefined} />
    </div>
  )
}

/** 分型逐组快速输入（M6.4-A）：按动作 measurement 渲染对应输入控件与校验 */
function SetForm({ measurement = 'weight_reps', onDone, onUndo, canUndo, rpeOpen, setRpeOpen,
                   suggestWeight, suggestReps }: {
  measurement: MeasurementType
  onDone: (s: LoggedSet) => void
  onUndo: () => void; canUndo: boolean
  rpeOpen: boolean; setRpeOpen: (v: boolean) => void
  suggestWeight?: number | null; suggestReps?: number
}) {
  const [weight, setWeight] = useState(suggestWeight != null ? String(suggestWeight) : '')
  const [reps, setReps] = useState(suggestReps ? String(suggestReps) : '')
  const [added, setAdded] = useState('')
  const [assist, setAssist] = useState('')
  const [minutes, setMinutes] = useState('')
  const [seconds, setSeconds] = useState('')
  const [distance, setDistance] = useState('')
  const [rpe, setRpe] = useState('')
  const [warmup, setWarmup] = useState(false)
  const [formError, setFormError] = useState('')
  const n = parseTrainingNumber

  const submit = () => {
    const draft = {
      type: measurement,
      weight: n(weight), reps: n(reps), added: n(added), assist: n(assist),
      minutes: n(minutes), seconds: n(seconds), distance: n(distance), rpe: n(rpe),
    }
    if (Object.values(draft).some((v) => v === undefined)) {
      setFormError('输入需为有效数字'); return
    }
    const invalid = validateSetDraft(draft)
    if (invalid) { setFormError(invalid); return }
    setFormError('')
    const at = new Date().toISOString()
    if (measurement === 'weight_reps') {
      onDone({ type: 'weight_reps', weight_kg: draft.weight as number, reps: draft.reps as number,
               rpe: draft.rpe ?? undefined, warmup, at })
    } else if (measurement === 'bodyweight_reps') {
      onDone({ type: 'bodyweight_reps', reps: draft.reps as number,
               added_weight_kg: draft.added ?? undefined, rpe: draft.rpe ?? undefined, warmup, at })
    } else if (measurement === 'assisted_reps') {
      onDone({ type: 'assisted_reps', reps: draft.reps as number,
               assistance_kg: draft.assist as number, rpe: draft.rpe ?? undefined, warmup, at })
    } else if (measurement === 'duration') {
      onDone({ type: 'duration',
               duration_seconds: (draft.minutes || 0) * 60 + (draft.seconds || 0), warmup, at })
    } else {
      onDone({ type: 'distance_time', distance_m: draft.distance as number,
               duration_seconds: (draft.minutes || 0) * 60 + (draft.seconds || 0), warmup, at })
    }
    // 连续记录：数值保留（组间多不变），RPE/热身复位
    setRpe(''); setWarmup(false)
  }

  const step = (cur: string, set: (v: string) => void, d: number, integer = false) => {
    setFormError('')
    const v = n(cur)
    const base = typeof v === 'number' ? (integer ? Math.floor(v) : v) : 0
    const next = integer ? base + d : Math.round((base + d) * 100) / 100
    if (next < 0.01) return
    set(String(next))
  }

  const stepBtn = 'flex h-9 flex-1 items-center justify-center rounded-lg border border-line ' +
    'bg-surface text-xs font-medium text-muted transition-colors hover:border-lineStrong hover:text-ink ' +
    'disabled:opacity-40'
  const big = 'input nums h-12 rounded-xl text-center text-lg font-semibold'
  const unit = 'pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted'
  const rpeToggle = (
    <button className={`flex size-11 shrink-0 items-center justify-center rounded-xl border transition-colors ${
      rpeOpen ? 'border-accent-deep/40 bg-accent-soft text-accent-deep'
              : 'border-line bg-surface text-muted'}`}
            onClick={() => setRpeOpen(!rpeOpen)}
            aria-expanded={rpeOpen} aria-label="展开 RPE">
      {rpeOpen ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
    </button>
  )
  const rpeRow = rpeOpen && (
    <input className="input nums input-sm mt-2 animate-fade-up text-center" placeholder="RPE（可选，1-10）"
           inputMode="decimal" value={rpe}
           onChange={(e) => { setRpe(e.target.value); setFormError('') }} />
  )
  const errRow = formError && (
    <p className="mt-2 text-center text-xs font-medium text-red-600" role="alert">{formError}</p>
  )
  const warmupChip = (
    <button className={`tag h-11 shrink-0 px-3 transition-colors ${
      warmup ? 'bg-amber-400 text-amber-950' : 'border border-line bg-surface text-muted'}`}
            onClick={() => { setWarmup((w) => !w); setFormError('') }} aria-pressed={warmup}>
      热身
    </button>
  )

  return (
    <div className="border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      {measurement === 'weight_reps' && (
        <>
          <div className="flex items-center gap-2">
            {warmupChip}
            <div className="relative flex-1">
              <input className={big} placeholder="重量" inputMode="decimal" value={weight}
                     onChange={(e) => { setWeight(e.target.value); setFormError('') }} />
              <span className={unit}>kg</span>
            </div>
            <div className="relative flex-1">
              <input className={big} placeholder="次数" inputMode="numeric" value={reps}
                     onChange={(e) => { setReps(e.target.value); setFormError('') }} />
              <span className={unit}>次</span>
            </div>
            {rpeToggle}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex flex-1 items-center gap-1.5">
              <button className={stepBtn} onClick={() => step(weight, setWeight, -2.5)} disabled={!weight}
                      aria-label="重量减 2.5 公斤">−2.5</button>
              <button className={stepBtn} onClick={() => step(weight, setWeight, 2.5)}
                      aria-label="重量加 2.5 公斤">+2.5</button>
            </div>
            <div className="flex flex-1 items-center gap-1.5">
              <button className={stepBtn} onClick={() => step(reps, setReps, -1, true)} disabled={!reps}
                      aria-label="次数减 1">−1</button>
              <button className={stepBtn} onClick={() => step(reps, setReps, 1, true)}
                      aria-label="次数加 1">+1</button>
            </div>
          </div>
          {rpeRow}{errRow}
        </>
      )}
      {(measurement === 'bodyweight_reps' || measurement === 'assisted_reps') && (
        <>
          <div className="flex items-center gap-2">
            {warmupChip}
            <div className="relative flex-1">
              <input className={big} placeholder="次数" inputMode="numeric" value={reps}
                     onChange={(e) => { setReps(e.target.value); setFormError('') }} />
              <span className={unit}>次</span>
            </div>
            <div className="relative flex-1">
              <input className={big}
                     placeholder={measurement === 'bodyweight_reps' ? '额外负重' : '辅助重量'}
                     inputMode="decimal"
                     value={measurement === 'bodyweight_reps' ? added : assist}
                     onChange={(e) => { measurement === 'bodyweight_reps'
                       ? setAdded(e.target.value) : setAssist(e.target.value); setFormError('') }} />
              <span className={unit}>kg</span>
            </div>
            {rpeToggle}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <div className="flex flex-1 items-center gap-1.5">
              <button className={stepBtn} onClick={() => step(reps, setReps, -1, true)} disabled={!reps}
                      aria-label="次数减 1">−1</button>
              <button className={stepBtn} onClick={() => step(reps, setReps, 1, true)}
                      aria-label="次数加 1">+1</button>
            </div>
          </div>
          {rpeRow}{errRow}
        </>
      )}
      {measurement === 'duration' && (
        <>
          <div className="flex items-center gap-2">
            {warmupChip}
            <div className="relative flex-1">
              <input className={big} placeholder="分" inputMode="numeric" value={minutes}
                     onChange={(e) => { setMinutes(e.target.value); setFormError('') }} />
              <span className={unit}>分</span>
            </div>
            <div className="relative flex-1">
              <input className={big} placeholder="秒" inputMode="numeric" value={seconds}
                     onChange={(e) => { setSeconds(e.target.value); setFormError('') }} />
              <span className={unit}>秒</span>
            </div>
          </div>
          {errRow}
        </>
      )}
      {measurement === 'distance_time' && (
        <>
          <div className="flex items-center gap-2">
            {warmupChip}
            <div className="relative flex-1">
              <input className={big} placeholder="距离" inputMode="decimal" value={distance}
                     onChange={(e) => { setDistance(e.target.value); setFormError('') }} />
              <span className={unit}>米</span>
            </div>
            <div className="relative flex-1">
              <input className={big} placeholder="分" inputMode="numeric" value={minutes}
                     onChange={(e) => { setMinutes(e.target.value); setFormError('') }} />
              <span className={unit}>分</span>
            </div>
            <div className="relative flex-1">
              <input className={big} placeholder="秒" inputMode="numeric" value={seconds}
                     onChange={(e) => { setSeconds(e.target.value); setFormError('') }} />
              <span className={unit}>秒</span>
            </div>
          </div>
          {errRow}
        </>
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
