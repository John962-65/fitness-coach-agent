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
import CardioTimer, { createCardioState } from '../components/workout/CardioTimer'
import HiitRunner, { createHiitRun, createIdleHiitRun, HiitPlanner } from '../components/workout/HiitRunner'
import { hiitPlanExerciseId } from '../lib/hiit'
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
  const [addingCardio, setAddingCardio] = useState(false)
  const [hiitPlanning, setHiitPlanning] = useState(false)
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
        const populate = () => {
          const hiitPlan = tpl.hiit
          const hiitIndex = tpl.hiit_index ?? tpl.entries.length
          const addHiit = () => {
            if (!hiitPlan) return
            useApp.getState().addFreeExercise({
              exercise_id: hiitPlanExerciseId(hiitPlan),
              name: hiitPlan.name, activity: 'hiit', hiitPlan,
              hiitRun: createIdleHiitRun(), measurement: 'duration',
              target: { sets: '—', reps: '—', weight: null }, logged: [],
            })
          }
          for (let i = 0; i <= tpl.entries.length; i++) {
            if (i === hiitIndex) addHiit()
            const en = tpl.entries[i]
            if (!en) continue
            useApp.getState().addFreeExercise({
              exercise_id: en.exercise_id, name: en.name,
              measurement: en.measurement, activity: en.activity,
              cardio: en.activity === 'cardio' ? createCardioState() : undefined,
              supersetGroup: en.superset_group,
              target: { sets: '—', reps: '—', weight: null }, logged: [],
            })
          }
        }
        const begin = () => {
          startFreeSession({ label, templateId: tid })
          populate()
        }
        const rr = startFreeSession({ label, templateId: tid })
        if (rr.resumed) return        // 同模板会话恢复：已预填，直接继续
        if (rr.kept) {
          const cur = useApp.getState().session!
          const n = cur.entries.reduce((s, e) => s + e.logged.filter((l) => !l.warmup).length, 0)
          switchBeginRef.current = begin
          setSwitchPrompt({
            activeLabel: `${cur.day === 'free' ? '自由训练' : cur.day}（已记录 ${n} 组）`,
            activeHref: '/workout/free', begin,
          })
          return
        }
        populate()
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
  const hiitCount = entries.filter((e) => e.activity === 'hiit').length
  // P5-A：复杂组容量=各执行段求和（与后端 exercise_metrics.set_volume 同公式）
  const segVolume = (l: LoggedSet): number => {
    const m = l as { method?: string; segments?: Record<string, number>[] }
    if (m.method && m.method !== 'straight_set' && Array.isArray(m.segments)) {
      const t = l.type || 'weight_reps'
      return m.segments.reduce((acc, g) =>
        acc + (t === 'weight_reps' ? (g.weight_kg || 0) : (g.added_weight_kg || 0))
          * (g.reps || 0), 0)
    }
    return NaN
  }
  const volume = entries.reduce((n, e) =>
    n + e.logged.filter((l) => !l.warmup)
      .reduce((m, l) => {
        const sv = segVolume(l)
        if (!Number.isNaN(sv)) return m + sv
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
          method: (l as { method?: string }).method,
          segments: (l as { segments?: unknown[] }).segments,
          weight_kg: l.type === 'weight_reps' ? l.weight_kg : undefined,
          added_weight_kg: l.type === 'bodyweight_reps' ? l.added_weight_kg : undefined,
          assistance_kg: l.type === 'assisted_reps' ? l.assistance_kg : undefined,
          reps: 'reps' in l ? l.reps : undefined,
          duration_seconds: 'duration_seconds' in l ? l.duration_seconds : undefined,
          distance_m: 'distance_m' in l ? l.distance_m : undefined,
          rpe: 'rpe' in l ? l.rpe : undefined,
          hiit: 'hiit' in l ? l.hiit : undefined,
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
            <div className="grid w-full grid-cols-3 gap-2">
              <Button variant="ghost" onClick={() => setAddingFree(true)}>
                <Plus size={16} /> 力量动作
              </Button>
              <Button variant="ghost" onClick={() => setAddingCardio(true)}>
                <Plus size={16} /> 有氧
              </Button>
              <Button variant="ghost" onClick={() => setHiitPlanning(true)}>
                <Plus size={16} /> HIIT
              </Button>
            </div>
          </div>
        )}

        {entries.map((e, idx) => (
          <ExerciseBlock key={idx} idx={idx} entry={e} isFree={isFree}
                         onPickReplace={() => setPickerIdx(idx)}
                         onRemove={() => removeEntry(idx)} />
        ))}

        {isFree && entries.length > 0 && (
          <>
            <div className="grid grid-cols-3 gap-2">
              <Button variant="ghost" onClick={() => setAddingFree(true)}>
                <Plus size={16} /> 力量动作
              </Button>
              <Button variant="ghost" onClick={() => setAddingCardio(true)}>
                <Plus size={16} /> 有氧
              </Button>
              <Button variant="ghost" onClick={() => setHiitPlanning(true)}>
                <Plus size={16} /> HIIT
              </Button>
            </div>
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
      {/* P5-B：有氧动作选择（activity=cardio） */}
      {addingCardio && (
        <ExercisePicker cardioOnly
          onClose={() => setAddingCardio(false)}
          onPick={(ex) => addFreeExercise({
            exercise_id: ex.id, name: ex.name,
            measurement: ex.measurement === 'distance_time' ? 'distance_time' : 'duration',
            activity: 'cardio', cardio: createCardioState(),
            target: { sets: '—', reps: '—', weight: null }, logged: [],
          })}
        />
      )}
      {/* P5-B：HIIT 快速编排 */}
      {hiitPlanning && (
        <Sheet open onClose={() => setHiitPlanning(false)} title="编排间歇训练">
          <HiitPlanner uid={uid} onStart={(plan) => {
            addFreeExercise({
              exercise_id: hiitPlanExerciseId(plan),
              name: plan.name, activity: 'hiit', hiitPlan: plan,
              hiitRun: createHiitRun(), measurement: 'duration',
              target: { sets: '—', reps: '—', weight: null }, logged: [],
            })
            setHiitPlanning(false)
          }} />
        </Sheet>
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
          {hiitCount > 1 && (
            <p className="mt-3 text-xs text-amber-700" role="alert">
              一个模板目前只支持一个 HIIT；请移除多余条目后再保存，其他动作不会丢失。
            </p>
          )}
          <Button block className="mt-3"
                  disabled={!templateName.trim() || hiitCount > 1}
                  onClick={async () => {
                    try {
                      const hiitEntry = entries.find((e) => e.activity === 'hiit' && e.hiitPlan)
                      await api.saveTrainingTemplate(uid, {
                        name: templateName.trim(),
                        note: templateNote.trim() || undefined,
                        entries: entries.filter((e) => e.activity !== 'hiit').map((e) => ({
                          exercise_id: (e.replaced_with ? e.replace_exercise_id : e.exercise_id) || '',
                          name: e.replaced_with || e.name,
                          measurement: e.measurement,
                          activity: e.activity === 'cardio' ? 'cardio' : undefined,
                          superset_group: e.supersetGroup,
                        })),
                        ...(hiitEntry?.hiitPlan
                          ? { hiit: hiitEntry.hiitPlan,
                              hiit_index: entries.indexOf(hiitEntry) } : {}),
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
  const updateEntry = useApp((s) => s.updateEntry)
  const removeLastSet = useApp((s) => s.removeLastSet)
  const startRest = useApp((s) => s.startRest)
  const setEntryGroup = useApp((s) => s.setEntryGroup)
  const drafts = useApp((s) => s.session?.drafts || {})
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
          {(!entry.activity || entry.activity === 'strength') && (
            <button className="btn-plain" onClick={onPickReplace}>
              <Repeat2 size={15} /> 替换
            </button>
          )}
          {isFree && (
            <button className="btn-plain !text-red-500" onClick={onRemove} aria-label="移除动作">
              移除
            </button>
          )}
        </div>
      </div>
      {(!entry.activity || entry.activity === 'strength') && (
        <>
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
          <SupersetBanner idx={idx} entry={entry} />
        </>
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
              {(l as { method?: string }).method && (
                <span className="tag bg-accent-soft text-accent-deep">
                  {{ drop_set: '递减', rest_pause: '休息暂停', unilateral: '单侧' }[
                    (l as { method?: string }).method as string] ?? ''}
                </span>
              )}
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

      {/* P5-B：有氧/HIIT 条目渲染执行器（无逐组输入） */}
      {entry.activity === 'cardio' ? (
        <CardioTimer idx={idx} entry={entry}
                     onUpdate={(patch) => updateEntry(idx, patch)} onLog={logSet}
                     onUndo={removeLastSet} />
      ) : entry.activity === 'hiit' ? (
        <HiitRunner idx={idx} entry={entry}
                    onUpdate={(patch) => updateEntry(idx, patch)} onLog={logSet} />
      ) : (
        <SetForm measurement={entry.measurement || 'weight_reps'}
                 onDone={(s) => { logSet(idx, s); if (!s.warmup) startRest() }}
                 onUndo={() => removeLastSet(idx)}
                 canUndo={entry.logged.length > 0}
                 rpeOpen={rpeOpen} setRpeOpen={setRpeOpen}
                 suggestWeight={prevWeight} suggestReps={Number(entry.target.reps) || undefined}
                 draftIdx={idx} initialDraft={drafts[idx]}
                 lastLogged={entry.logged.filter((l) => !l.warmup).slice(-1)[0]} />
      )}
    </div>
  )
}

/** 分型逐组快速输入（M6.4-A）：按动作 measurement 渲染对应输入控件与校验。
 *  M6.4-B B4.2：未提交输入镜像到 store（drafts），进教学页返回/刷新不丢。 */
function SetForm({ measurement = 'weight_reps', onDone, onUndo, canUndo, rpeOpen, setRpeOpen,
                   suggestWeight, suggestReps, draftIdx, initialDraft, lastLogged }: {
  measurement: MeasurementType
  onDone: (s: LoggedSet) => void
  onUndo: () => void; canUndo: boolean
  rpeOpen: boolean; setRpeOpen: (v: boolean) => void
  suggestWeight?: number | null; suggestReps?: number
  draftIdx: number
  initialDraft?: import('../store').SetDraftValues
  lastLogged?: LoggedSet
}) {
  const setEntryDraft = useApp((s) => s.setEntryDraft)
  const [weight, setWeightRaw] = useState(initialDraft?.weight
    ?? (suggestWeight != null ? String(suggestWeight) : ''))
  const [reps, setRepsRaw] = useState(initialDraft?.reps
    ?? (suggestReps ? String(suggestReps) : ''))
  const [added, setAddedRaw] = useState(initialDraft?.added ?? '')
  const [assist, setAssistRaw] = useState(initialDraft?.assist ?? '')
  const [minutes, setMinutesRaw] = useState(initialDraft?.minutes ?? '')
  const [seconds, setSecondsRaw] = useState(initialDraft?.seconds ?? '')
  const [distance, setDistanceRaw] = useState(initialDraft?.distance ?? '')
  const [rpe, setRpeRaw] = useState(initialDraft?.rpe ?? '')
  const [warmup, setWarmupRaw] = useState(initialDraft?.warmup ?? false)
  // 同名 setter：本地更新 + 草稿镜像进 store（B4.2 教学往返不丢）
  const mirror = <K extends keyof import('../store').SetDraftValues>(
    key: K, v: import('../store').SetDraftValues[K]) => setEntryDraft(draftIdx, { [key]: v })
  const setWeight = (v: string) => { setWeightRaw(v); mirror('weight', v) }
  const setReps = (v: string) => { setRepsRaw(v); mirror('reps', v) }
  const setAdded = (v: string) => { setAddedRaw(v); mirror('added', v) }
  const setAssist = (v: string) => { setAssistRaw(v); mirror('assist', v) }
  const setMinutes = (v: string) => { setMinutesRaw(v); mirror('minutes', v) }
  const setSeconds = (v: string) => { setSecondsRaw(v); mirror('seconds', v) }
  const setDistance = (v: string) => { setDistanceRaw(v); mirror('distance', v) }
  const setRpe = (v: string) => { setRpeRaw(v); mirror('rpe', v) }
  const setWarmup = (v: boolean | ((p: boolean) => boolean)) => {
    setWarmupRaw((prev) => {
      const nv = typeof v === 'function' ? v(prev) : v
      queueMicrotask(() => mirror('warmup', nv))
      return nv
    })
  }
  const [formError, setFormError] = useState('')
  const n = parseTrainingNumber
  // P5-A：组法（普通=缺省；递减/休息暂停/单侧 → 分段编辑）
  const [method, setMethodRaw] = useState(initialDraft?.method ?? '')
  const [segments, setSegmentsRaw] = useState<Record<string, string>[]>(
    (() => {
      try { return initialDraft?.segments ? JSON.parse(initialDraft.segments) as Record<string, string>[] : [] }
      catch { return [] }
    })())
  const setMethod = (m: string) => {
    setMethodRaw(m); mirror('method', m)
    if (m === '') { setSegmentsRaw([]); mirror('segments', '') }
    else if (segments.length === 0) {
      const init: Record<string, string>[] = m === 'unilateral'
        ? [{ side: 'left', weight: weight || String(suggestWeight ?? ''), reps: reps || '' },
           { side: 'right', weight: weight || String(suggestWeight ?? ''), reps: '' }]
        : [{ weight: weight || String(suggestWeight ?? ''), reps: reps || '', rest: '' },
           ...(m === 'drop_set' ? [{ weight: '', reps: '', rest: '' }] : [])]
      setSegmentsRaw(init); mirror('segments', JSON.stringify(init))
    }
    setFormError('')
  }
  const updateSeg = (i: number, key: string, v: string) => {
    const next = segments.map((sg, j) => (j === i ? { ...sg, [key]: v } : sg))
    setSegmentsRaw(next); mirror('segments', JSON.stringify(next)); setFormError('')
  }
  const addSeg = () => {
    const blank: Record<string, string> = method === 'unilateral'
      ? { side: segments.length === 0 ? 'left' : 'right', weight: weight || '', reps: '' }
      : { weight: '', reps: '', rest: method === 'rest_pause' ? '20' : '' }
    const next = [...segments, blank].slice(0, 6)
    setSegmentsRaw(next); mirror('segments', JSON.stringify(next))
  }
  const removeSeg = (i: number) => {
    const next = segments.filter((_, j) => j !== i)
    setSegmentsRaw(next); mirror('segments', JSON.stringify(next))
  }
  // P5-A：一键复制上一组（数值回填；不自动提交——提交仍需用户按确认）
  const copyLast = () => {
    if (!lastLogged) return
    const l = lastLogged
    if (l.type === 'weight_reps') { setWeight(String(l.weight_kg)); setReps(String(l.reps)) }
    else if (l.type === 'bodyweight_reps') { setReps(String(l.reps)); setAdded(String(l.added_weight_kg ?? '')) }
    else if (l.type === 'assisted_reps') { setReps(String(l.reps)); setAssist(String(l.assistance_kg)) }
    else if (l.type === 'duration') { setMinutes(String(Math.floor((l.duration_seconds || 0) / 60))); setSeconds(String((l.duration_seconds || 0) % 60)) }
    else if (l.type === 'distance_time') { setDistance(String(l.distance_m)); setMinutes(String(Math.floor((l.duration_seconds || 0) / 60))); setSeconds(String((l.duration_seconds || 0) % 60)) }
    if ('rpe' in l && l.rpe != null) setRpe(String(l.rpe))
    setFormError('')
  }

  const submit = () => {
    // P5-A：复杂组提交——segments 合成（不经过主输入校验；本质量在执行段）
    const at0 = new Date().toISOString()
    if (method === 'drop_set' || method === 'rest_pause' || method === 'unilateral') {
      const segs0 = segments.filter((sg) => n(sg.reps) !== undefined
        && (method === 'unilateral'
          ? (n(sg.weight) !== undefined || n(sg.added) !== undefined)
          : n(sg.weight) !== undefined))
      if (segs0.length < 2) {
        setFormError('复杂组至少需要 2 个有效执行段'); return
      }
      const built0 = segs0.map((sg) => method === 'unilateral'
        ? (measurement === 'bodyweight_reps'
            ? { side: sg.side as 'left' | 'right', reps: n(sg.reps) as number,
                ...(n(sg.added) != null ? { added_weight_kg: n(sg.added) } : {}) }
            : { side: sg.side as 'left' | 'right', weight_kg: n(sg.weight) as number,
                reps: n(sg.reps) as number })
        : (measurement === 'bodyweight_reps'
            ? { added_weight_kg: n(sg.added) ?? 0, reps: n(sg.reps) as number,
                ...(n(sg.rest) != null ? { rest_seconds: n(sg.rest) } : {}) }
            : { weight_kg: n(sg.weight) as number, reps: n(sg.reps) as number,
                ...(n(sg.rest) != null ? { rest_seconds: n(sg.rest) } : {}) }))
      onDone({ method: method as import('../types').SetMethod,
               segments: built0, warmup, at: at0 } as LoggedSet)
      setSegmentsRaw(segments.map((sg) => ({ ...sg, reps: '' })))
      mirror('segments', JSON.stringify(segments.map((sg) => ({ ...sg, reps: '' }))))
      setRpe(''); setWarmup(false)
      return
    }
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

  const methodChips = (measurement === 'weight_reps' || measurement === 'bodyweight_reps'
    || measurement === 'assisted_reps') && (
    <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="训练方法">
      <span className="text-2xs text-muted">组法</span>
      {([['', '普通'], ['drop_set', '递减'], ['rest_pause', '休息暂停'],
         ['unilateral', '单侧']] as const).map(([m, label]) => (
        <button key={m || 'straight'} onClick={() => setMethod(m)}
                className={`tag min-h-7 px-2 transition-colors ${
                  method === m ? 'bg-night text-white'
                    : 'border border-line bg-surface text-muted'}`}
                aria-pressed={method === m}>{label}</button>
      ))}
      {lastLogged && method === '' && (
        <button onClick={copyLast}
                className="tag min-h-7 border border-line bg-surface px-2 text-muted
                           transition-colors hover:border-accent-deep/40 hover:text-ink">
          复制上一组
        </button>
      )}
    </div>
  )

  return (
    <div className="border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      {methodChips}
      {method !== '' && (
        /* P5-A：分段编辑器（递减/休息暂停=负荷段；单侧=左右段） */
        <div className="mb-2 space-y-1.5">
          {segments.map((sg, i) => (
            <div key={i} className="flex items-center gap-1.5 rounded-xl border border-line
                                    bg-surface p-1.5">
              {method === 'unilateral' ? (
                <span className={`tag shrink-0 ${sg.side === 'left'
                  ? 'bg-accent-soft text-accent-deep' : 'bg-ink/6 text-muted'}`}>
                  {sg.side === 'left' ? '左' : '右'}
                </span>
              ) : (
                <span className="shrink-0 px-1 text-2xs text-muted">段{i + 1}</span>
              )}
              {measurement !== 'bodyweight_reps' && (
                <input className="input nums input-sm min-w-0 flex-1 text-center"
                       placeholder="重量 kg" inputMode="decimal" value={sg.weight ?? ''}
                       onChange={(e) => updateSeg(i, 'weight', e.target.value)}
                       aria-label={`段${i + 1} 重量`} />
              )}
              {measurement === 'bodyweight_reps' && (
                <input className="input nums input-sm min-w-0 flex-1 text-center"
                       placeholder="附加 kg" inputMode="decimal" value={sg.added ?? ''}
                       onChange={(e) => updateSeg(i, 'added', e.target.value)}
                       aria-label={`段${i + 1} 附加重量`} />
              )}
              <input className="input nums input-sm min-w-0 flex-1 text-center"
                     placeholder="次数" inputMode="numeric" value={sg.reps ?? ''}
                     onChange={(e) => updateSeg(i, 'reps', e.target.value)}
                     aria-label={`段${i + 1} 次数`} />
              {method === 'rest_pause' && (
                <input className="input nums input-sm w-16 shrink-0 text-center"
                       placeholder="休息s" inputMode="numeric" value={sg.rest ?? ''}
                       onChange={(e) => updateSeg(i, 'rest', e.target.value)}
                       aria-label={`段${i + 1} 段间休息秒`} />
              )}
              <button className="shrink-0 px-1 text-2xs text-red-500"
                      onClick={() => removeSeg(i)} aria-label={`删除段${i + 1}`}>删</button>
            </div>
          ))}
          <div className="flex gap-2">
            <button className="btn-plain flex-1 justify-center text-xs" onClick={addSeg}>
              + 加一段
            </button>
          </div>
        </div>
      )}
      {method === '' && measurement === 'weight_reps' && (
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
      {method === '' && (measurement === 'bodyweight_reps' || measurement === 'assisted_reps') && (
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

/** P5-A：超级组执行横幅——轮次推进提示、轮间/动作间休息、配置与解除。
 *  状态派生自已记录组数（不编造完成记录）；轮次/休息配置存 session
 *  （刷新恢复）。 */
function SupersetBanner({ idx, entry }: { idx: number; entry: SessionEntry }) {
  const session = useApp((s) => s.session)
  const entries = session?.entries ?? []
  const cfgMap = session?.supersetConfig || {}
  const setSupersetConfig = useApp((s) => s.setSupersetConfig)
  const setEntryGroup = useApp((s) => s.setEntryGroup)
  const startRestAt = useApp((s) => s.startRest)
  const [configOpen, setConfigOpen] = useState(false)
  const group = entry.supersetGroup
  if (!group) return null
  const cfg = cfgMap[group] || { rounds: 0, restBetween: 30, restRounds: 90 }
  const members = entries
    .map((e, i) => ({ e, i }))
    .filter(({ e }) => e.supersetGroup === group)
  const doneBy = members.map(({ e }) => e.logged.filter((l) => !l.warmup).length)
  // 自由训练可能无目标组数（0）——不参与 min，否则轮次永远停在 1
  const target = Number(entry.target.sets) || 0
  const minDone = target > 0
    ? Math.min(...doneBy, target)
    : Math.min(...doneBy)
  const currentRound = Math.min(minDone + 1, cfg.rounds || minDone + 1)
  // 下一动作 = 组内完成组数最少的第一个
  const next = members
    .filter(({ e }) => e.logged.filter((l) => !l.warmup).length
      === Math.min(...doneBy))
    [0]
  const isNext = next?.i === idx
  const roundJustDone = doneBy.every((d) => d >= minDone && d > 0)
    && doneBy.every((d) => d === doneBy[0])
  return (
    <div className="mx-4 mb-2.5 rounded-xl border border-accent/30 bg-accent/5 p-2.5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="tag bg-night text-white">超级组 {group}</span>
        {cfg.rounds > 0 && (
          <span className="nums text-muted">第 {Math.min(currentRound, cfg.rounds)}/{cfg.rounds} 轮</span>
        )}
        {isNext && next && (
          <span className="font-medium text-accent-deep">← 本动作现在轮到</span>
        )}
        {!isNext && next && (
          <span className="text-muted">下一动作：{next.e.replaced_with || next.e.name}</span>
        )}
        <button className="ml-auto text-2xs text-muted underline underline-offset-2"
                onClick={() => setConfigOpen(!configOpen)}>
          {configOpen ? '收起' : '轮次/休息'}
        </button>
        <button className="text-2xs text-red-500"
                aria-label={`解除超级组${group}`}
                onClick={() => setEntryGroup(idx, undefined)}>解除</button>
      </div>
      {configOpen && (
        <div className="mt-2 space-y-1.5 border-t border-accent/20 pt-2 text-xs">
          {[
            ['rounds', '目标轮次', cfg.rounds],
            ['restBetween', '动作间休息（秒）', cfg.restBetween],
            ['restRounds', '轮间休息（秒）', cfg.restRounds],
          ].map(([key, label, val]) => (
            <label key={key as string} className="flex items-center justify-between gap-2">
              <span className="text-muted">{label}</span>
              <input type="number" min={0} max={600} value={val as number}
                     aria-label={label as string}
                     className="input nums input-sm w-20 text-center"
                     onChange={(e) => setSupersetConfig(group, {
                       [key as 'rounds' | 'restBetween' | 'restRounds']:
                         Math.max(0, Number(e.target.value) || 0) })} />
            </label>
          ))}
          <p className="text-2xs leading-relaxed text-faint">
            提示只做组织辅助，不自动编造完成记录；跳过/补做/改顺序由你直接操作对应动作卡。
          </p>
        </div>
      )}
      {roundJustDone && cfg.rounds > 0 && currentRound <= cfg.rounds && (
        <button className="btn-soft btn mt-2 w-full text-xs"
                onClick={() => startRestAt()}>
          第 {currentRound - 1} 轮完成 · 开始轮间休息 {cfg.restRounds}s
        </button>
      )}
    </div>
  )
}
