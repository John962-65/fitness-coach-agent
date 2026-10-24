import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Dumbbell, Salad, Scale } from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Empty, ErrorBox, Input, PageHeader, Segmented, Select, Sheet,
  Skeleton, Spinner, Stat, Tag, Textarea,
} from '../components/Bits'
import { buildCorrectedData, initSetEdit, ExerciseEdit, SetEdit } from '../lib/checkin'
import { parseTrainingNumber, validateSetDraft } from '../lib/validate'
import { formatSetRecord } from '../lib/setDisplay'
import { useApp } from '../store'
import { Checkin, PeriodSummary, TrainingCalendar } from '../types'

const TYPE_META: Record<string, { label: string; icon: typeof Dumbbell }> = {
  training: { label: '训练', icon: Dumbbell },
  body: { label: '身体', icon: Scale },
  diet: { label: '饮食', icon: Salad },
}

const MUSCLE_LABEL: Record<string, string> = {
  chest: '胸', back: '背', shoulders: '肩', biceps: '二头', triceps: '三头',
  quads: '股四头', hamstrings: '腘绳', glutes: '臀', calves: '小腿', core: '核心',
  other: '其他',
}

export default function History() {
  const uid = useApp((s) => s.uid)
  const [view, setView] = useState<'list' | 'calendar'>('list')
  const [checkins, setCheckins] = useState<Checkin[] | null>(null)
  const [error, setError] = useState('')
  const [correcting, setCorrecting] = useState<Checkin | null>(null)
  // 列表筛选（客户端过滤，数据取最近 50 条）
  const [typeFilter, setTypeFilter] = useState('')
  const [q, setQ] = useState('')
  const [listOffset, setListOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)

  const load = useCallback((offset = 0) => {
    api.checkins(uid, 50, undefined, offset)
      .then((r) => {
        setCheckins((prev) => (offset > 0 && prev ? [...prev, ...r.checkins] : r.checkins))
        setListOffset(offset)
        setHasMore(r.checkins.length >= 50)
      })
      .catch((e) => setError(e.message))
  }, [uid])
  useEffect(() => { load(0) }, [load])

  const filtered = useMemo(() => (checkins || []).filter((c) => {
    if (typeFilter && c.type !== typeFilter) return false
    if (q.trim()) {
      const needle = q.trim().toLowerCase()
      const hay = JSON.stringify(c.data).toLowerCase()
      if (!hay.includes(needle)) return false
    }
    return true
  }), [checkins, typeFilter, q])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!checkins) return <Spinner />

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="训练历史" sub="逐组记录 · 纠错保留修订痕迹 · 长期回顾" />
      <Segmented className="mb-4"
        options={[
          { value: 'list', label: '记录列表' },
          { value: 'calendar', label: '日历与统计' },
        ]}
        value={view} onChange={setView} />

      {view === 'calendar'
        ? <CalendarView uid={uid} onCorrect={setCorrecting} />
        : (
          <>
            <div className="mb-3 flex gap-2">
              <Select className="!w-32" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}
                      aria-label="按类型筛选">
                <option value="">全部类型</option>
                <option value="training">训练</option>
                <option value="body">身体</option>
                <option value="diet">饮食</option>
              </Select>
              <Input placeholder="搜索动作 / 备注…" value={q}
                     onChange={(e) => setQ(e.target.value)} aria-label="搜索记录" />
            </div>

            {filtered.length === 0 && (
              <Empty title="没有匹配的记录">
                {checkins.length === 0 ? '完成第一次训练后，记录会出现在这里。' : '换个筛选条件试试。'}
              </Empty>
            )}
            <div className="space-y-3">
              {filtered.map((c) => <CheckinCard key={c.id} c={c} onCorrect={() => setCorrecting(c)} />)}
            </div>
            {hasMore && (
              <button className="btn-ghost w-full" onClick={() => load(listOffset + 50)}>
                加载更多
              </button>
            )}
          </>
        )}

      {correcting && (
        <CorrectModal checkin={correcting} uid={uid}
          onClose={() => setCorrecting(null)} onSaved={() => { setCorrecting(null); load() }} />
      )}
    </div>
  )
}

/* ---------------- 记录卡片（列表与日历共用） ---------------- */

function CheckinCard({ c, onCorrect }: { c: Checkin; onCorrect: () => void }) {
  const meta = TYPE_META[c.type] || TYPE_META.training
  return (
    <div className="card">
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

      {c.revision > 0 && c.last_reason && (
        <p className="mb-2 -mt-1 rounded-lg bg-amber-50 px-2.5 py-1.5 text-xs leading-relaxed text-amber-800">
          修订 v{c.revision} 原因：{c.last_reason}
        </p>
      )}

      {c.type === 'training' && c.data.exercises?.length ? (
        <ul className="rows">
          {c.data.exercises.map((ex, i) => (
            <li key={i} className="py-2 first:pt-0 last:pb-0">
              {ex.set_logs?.length ? (
                <div>
                  <p className="text-sm font-medium">
                    {ex.name}
                    {ex.superset_group ? <Tag tone="blue" className="ml-1.5">超级组 {String(ex.superset_group)}</Tag> : null}
                    <span className="nums ml-1.5 text-xs text-muted">{ex.set_logs.length} 组</span>
                  </p>
                  <ul className="nums mt-1 space-y-0.5">
                    {ex.set_logs.map((l, j) => (
                      <li key={j} className="flex items-center gap-2 text-[13px] text-muted">
                        <span className="w-8 shrink-0 text-faint">#{j + 1}</span>
                        {l.warmup && <span className="tag bg-amber-50 text-amber-700">热身</span>}
                        <span className="text-ink">{formatSetRecord(l)}</span>
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
        <button className="btn-plain text-accent-deep" onClick={onCorrect}>纠错这条记录</button>
      </div>
    </div>
  )
}

/* ---------------- 日历与周期统计（M6.3） ---------------- */

function CalendarView({ uid, onCorrect }: {
  uid: string; onCorrect: (c: Checkin) => void
}) {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [cal, setCal] = useState<TrainingCalendar | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [dayCheckins, setDayCheckins] = useState<Checkin[] | null>(null)
  const [periodDays, setPeriodDays] = useState<7 | 30 | 90>(30)
  const [summary, setSummary] = useState<PeriodSummary | null>(null)

  useEffect(() => {
    api.trainingCalendar(uid, year, month)
      .then(setCal).catch(() => setCal({ year, month, days: [] }))
  }, [uid, year, month])
  useEffect(() => {
    api.periodSummary(uid, periodDays)
      .then(setSummary).catch(() => setSummary(null))
  }, [uid, periodDays])
  // 当日记录按日期向服务端查询（M6.3.1：与日历聚合同口径），分页拉全
  useEffect(() => {
    if (!selected) { setDayCheckins(null); return }
    let alive = true
    setDayCheckins(null)
    ;(async () => {
      const all: Checkin[] = []
      try {
        for (let offset = 0; offset < 200; offset += 50) {
          const r = await api.checkins(uid, 50, selected, offset)
          if (!alive) return
          all.push(...r.checkins)
          if (r.checkins.length < 50) break
        }
      } catch { /* 查询失败按空处理 */ }
      if (alive) setDayCheckins(all)
    })()
    return () => { alive = false }
  }, [uid, selected])

  const byDate = useMemo(() => {
    const m = new Map<string, TrainingCalendar['days'][number]>()
    for (const d of cal?.days || []) m.set(d.date, d)
    return m
  }, [cal])

  // 周一起始的月历网格
  const grid = useMemo(() => {
    const first = new Date(year, month - 1, 1)
    const offset = (first.getDay() + 6) % 7
    const total = new Date(year, month, 0).getDate()
    const cells: (number | null)[] = Array(offset).fill(null)
    for (let d = 1; d <= total; d++) cells.push(d)
    while (cells.length % 7) cells.push(null)
    return cells
  }, [year, month])

  const moveMonth = (delta: number) => {
    const d = new Date(year, month - 1 + delta, 1)
    setYear(d.getFullYear()); setMonth(d.getMonth() + 1); setSelected(null)
  }

  const dayCheckinsList = dayCheckins || []
  const maxMuscle = summary ? Math.max(1, ...Object.values(summary.by_muscle)) : 1

  return (
    <div className="space-y-4">
      {/* 月历 */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <button className="btn-plain" onClick={() => moveMonth(-1)} aria-label="上个月">
            <ChevronLeft size={16} />
          </button>
          <p className="nums text-[15px] font-bold">{year} 年 {month} 月</p>
          <button className="btn-plain" onClick={() => moveMonth(1)} aria-label="下个月">
            <ChevronRight size={16} />
          </button>
        </div>
        <div className="grid grid-cols-7 gap-1 text-center text-2xs text-muted">
          {['一', '二', '三', '四', '五', '六', '日'].map((w) => <span key={w}>{w}</span>)}
        </div>
        <div className="mt-1 grid grid-cols-7 gap-1">
          {grid.map((d, i) => {
            if (d == null) return <span key={`e${i}`} />
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
            const info = byDate.get(dateStr)
            const isToday = dateStr === today.toISOString().slice(0, 10)
            return (
              <button key={dateStr} disabled={!info}
                      onClick={() => setSelected(info ? dateStr : null)}
                      className={`relative flex min-h-11 flex-col items-center justify-center rounded-lg
                                  text-[13px] transition-colors ${
                        info ? 'bg-accent-soft font-semibold text-accent-deep hover:bg-accent/40'
                             : 'text-muted'} ${
                        selected === dateStr ? 'ring-2 ring-accent-deep/50' : ''} ${
                        isToday ? 'outline outline-1 outline-night/30' : ''}`}>
                {d}
                {info && info.sessions > 1 && (
                  <span className="nums absolute bottom-0.5 text-[9px] font-bold">×{info.sessions}</span>
                )}
              </button>
            )
          })}
        </div>
        <p className="mt-2.5 text-2xs leading-relaxed text-faint">
          绿色 = 有训练的日期（×n 为同日多次）；点击查看当天完整记录。
        </p>
      </div>

      {/* 周期统计 */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-[15px] font-semibold">周期统计</h3>
          <Segmented className="!flex-none"
            options={[
              { value: '7', label: '7 天' },
              { value: '30', label: '30 天' },
              { value: '90', label: '90 天' },
            ]}
            value={String(periodDays) as '7' | '30' | '90'}
            onChange={(v) => setPeriodDays(Number(v) as 7 | 30 | 90)} />
        </div>
        {!summary ? <Skeleton className="h-24" /> : (
          <>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              <Stat value={summary.sessions} label={`训练次数（约 ${summary.per_week}/周）`} />
              <Stat value={summary.working_sets} label="工作组数" />
              <Stat value={summary.volume} label="容量 kg" />
              <Stat value={summary.avg_duration_min != null
                ? (summary.avg_duration_min >= 1 ? `${summary.avg_duration_min} 分` : '不足 1 分')
                : '—'}
                    label="平均时长" />
            </div>
            <div className="mt-3.5">
              <p className="mb-2 text-[13px] font-medium text-muted">
                肌群分布（按主肌群归口，一组只计一次）
              </p>
              {Object.keys(summary.by_muscle).length === 0 ? (
                <p className="text-xs text-muted">该周期内暂无训练。</p>
              ) : (
                <div className="space-y-1.5">
                  {Object.entries(summary.by_muscle).map(([m, n]) => (
                    <div key={m} className="flex items-center gap-2.5">
                      <span className="w-12 shrink-0 text-xs text-ink">{MUSCLE_LABEL[m] || m}</span>
                      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink/8">
                        <div className="h-full rounded-full bg-accent"
                             style={{ width: `${(n / maxMuscle) * 100}%` }} />
                      </div>
                      <span className="nums w-8 shrink-0 text-right text-xs text-muted">{n}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* 选中日期的完整记录（服务端按日期查询，不受列表窗口限制） */}
      {selected && (
        <div className="space-y-3">
          <h3 className="nums px-1 text-[15px] font-bold">{selected} 的记录</h3>
          {dayCheckins === null ? (
            <Skeleton className="h-24" />
          ) : dayCheckinsList.length === 0 ? (
            <Empty title="该日期没有训练记录" />
          ) : (
            dayCheckinsList.map((c) => <CheckinCard key={c.id} c={c} onCorrect={() => onCorrect(c)} />)
          )}
        </div>
      )}
    </div>
  )
}

/* ---------------- 逐组纠错（M6.1.1） ---------------- */

function CorrectModal({ checkin, uid, onClose, onSaved }: {
  checkin: Checkin; uid: string; onClose: () => void; onSaved: () => void
}) {
  // M6.1 P0：逐组编辑——set_logs 的每组 weight/reps/rpe 可改，
  // 热身标记与完成时间原样保留；未修改的组按原值回传，绝不丢组。
  const [edits, setEdits] = useState<ExerciseEdit[]>((checkin.data.exercises || []).map((ex) => {
    if (ex.set_logs?.length) {
      return { logs: ex.set_logs.map(initSetEdit) }
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
    // M6.1.1：纠错原因真必填（不再回退"修正记录"）；范围校验与训练执行共用一套规则
    if (!reason.trim()) {
      setError({ message: '请填写纠错原因——它会与原值一起留档，保证可追溯' })
      setSaving(false); return
    }
    const exercises = checkin.data.exercises || []
    for (let ei = 0; ei < exercises.length; ei++) {
      const ex = exercises[ei]
      const edit = edits[ei] || {}
      if (ex.set_logs?.length) {
        for (let li = 0; li < ex.set_logs.length; li++) {
          const l = ex.set_logs[li]
          const e = edit.logs?.[li]
          if (!e) continue
          // M6.4-A.1：按记录类型构建草稿，与训练执行共用同一套校验规则
          const n = parseTrainingNumber
          const draft = {
            type: l.type || 'weight_reps',
            weight: n(e.weight ?? ''), reps: n(e.reps ?? ''), rpe: n(e.rpe ?? ''),
            added: n(e.added ?? ''), assist: n(e.assist ?? ''),
            minutes: n(e.minutes ?? ''), seconds: n(e.seconds ?? ''),
            distance: n(e.distance ?? ''),
          }
          if (Object.values(draft).some((v) => v === undefined)) {
            setError({ message: `「${ex.name}」第 ${li + 1} 组存在无效数字` })
            setSaving(false); return
          }
          const invalid = validateSetDraft(draft)
          if (invalid) {
            setError({ message: `「${ex.name}」第 ${li + 1} 组：${invalid}` })
            setSaving(false); return
          }
        }
      } else {
        const n = parseTrainingNumber
        const w = n(edit.weight ?? '')
        const r = n(edit.reps ?? '')
        if (w === undefined || r === undefined) {
          setError({ message: `「${ex.name}」存在无效数字，请检查重量/次数` })
          setSaving(false); return
        }
        const invalid = validateSetDraft({ type: 'weight_reps', weight: w, reps: r })
        if (invalid) {
          setError({ message: `「${ex.name}」：${invalid}` })
          setSaving(false); return
        }
      }
    }
    const data = buildCorrectedData(checkin, edits)
    if (!data) {
      setError({ message: '存在无效的数字输入，请检查重量/次数/RPE' })
      setSaving(false); return
    }
    try {
      await api.correctCheckin(uid, checkin.id, {
        expected_revision: checkin.revision,
        data,
        reason: reason.trim(),
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
                  {ex.set_logs.map((l, li) => {
                    const e = edit.logs?.[li] || {}
                    const set = (k: keyof SetEdit) => (ev: { target: { value: string } }) =>
                      patchLog(ei, li, { [k]: ev.target.value } as Partial<SetEdit>)
                    const numInput = (label: string, k: keyof SetEdit, mode: 'decimal' | 'numeric',
                                      w2 = 'flex-1') => (
                      <Input className={`input-sm nums ${w2} text-center`} inputMode={mode}
                             placeholder={label} aria-label={`第 ${li + 1} 组${label}`}
                             value={e[k] ?? ''} onChange={set(k)} />
                    )
                    const t = l.type || 'weight_reps'
                    return (
                      <div key={li} className="flex items-center gap-1.5">
                        <span className={`flex size-6 shrink-0 items-center justify-center rounded-full text-2xs font-bold ${
                          l.warmup ? 'bg-amber-100 text-amber-700' : 'bg-accent-soft text-accent-deep'}`}>
                          {li + 1}
                        </span>
                        {l.warmup && <span className="tag shrink-0 bg-amber-50 text-amber-700">热身</span>}
                        <span className="nums shrink-0 text-xs text-muted">{formatSetRecord(l)}</span>
                        {t === 'weight_reps' && numInput('重量', 'weight', 'decimal')}
                        {t === 'bodyweight_reps' && numInput('额外负重', 'added', 'decimal')}
                        {t === 'assisted_reps' && numInput('辅助', 'assist', 'decimal')}
                        {(t === 'duration' || t === 'distance_time') && numInput('分', 'minutes', 'numeric', 'w-14')}
                        {(t === 'duration' || t === 'distance_time') && numInput('秒', 'seconds', 'numeric', 'w-14')}
                        {t === 'distance_time' && numInput('米', 'distance', 'decimal', 'w-20')}
                        {t !== 'duration' && t !== 'distance_time' && numInput('次数', 'reps', 'numeric')}
                        {t !== 'duration' && t !== 'distance_time' && (
                          <Input className="input-sm nums w-14 shrink-0 text-center" inputMode="decimal"
                                 placeholder="RPE" aria-label={`第 ${li + 1} 组 RPE`}
                                 value={e.rpe ?? ''} onChange={set('rpe')} />
                        )}
                      </div>
                    )
                  })}
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
