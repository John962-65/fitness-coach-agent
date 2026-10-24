import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  CalendarRange, ChevronRight, History as HistoryIcon, Pencil,
  Play, Plus, TriangleAlert,
} from 'lucide-react'
import { api } from '../api'
import {
  Button, Card, ErrorBox, Notice, PageHeader, PlainButton, Spinner, Tag,
} from '../components/Bits'
import { ExerciseCover } from '../components/media'
import { useApp } from '../store'
import { PlanResponse, PlanRevision, TrainingTemplate } from '../types'

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export default function Training() {
  const uid = useApp((s) => s.uid)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('')
  const [templates, setTemplates] = useState<TrainingTemplate[] | null>(null)
  const [versions, setVersions] = useState<PlanRevision[] | null>(null)
  const [showVersions, setShowVersions] = useState(false)
  const [restoreNote, setRestoreNote] = useState('')
  const navigate = useNavigate()

  const loadVersions = useCallback(() => {
    api.planRevisions(uid).then((r) => setVersions(r.revisions)).catch(() => setVersions([]))
  }, [uid])
  useEffect(() => { loadVersions() }, [loadVersions])

  const loadTemplates = useCallback(() => {
    api.trainingTemplates(uid).then((r) => setTemplates(r.templates)).catch(() => setTemplates([]))
  }, [uid])
  useEffect(() => { loadTemplates() }, [loadTemplates])

  const [offlineMode, setOfflineMode] = useState(false)
  useEffect(() => {
    api.plan(uid).then((p) => { api.cachePlan(uid, p); setPlan(p) })
      .catch((e) => {
        // 断网降级：用最近一次加载的计划展示（训练执行页同样降级）
        const cached = api.cachedPlan(uid)
        if ((e as { status?: number }).status === 0 && cached) {
          setPlan(cached); setOfflineMode(true)
        } else {
          setError(e.message)
        }
      })
  }, [uid])

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl space-y-3">
        <PageHeader title="训练" />
        <ErrorBox message={error} />
        <Link to="/coach" className="btn-ghost block text-center">去 AI 教练页完成建档</Link>
      </div>
    )
  }
  if (!plan) return <Spinner />

  const weekday = WEEKDAYS[new Date().getDay()]
  const today = plan.content.schedule.find((d) => d.day === weekday)
  const activeDay = selected || today?.day || plan.content.schedule[0]?.day || ''
  const active = plan.content.schedule.find((d) => d.day === activeDay)
  const deload = plan.content.deload
  const deloadActive = deload && deload.until >= new Date().toISOString().slice(0, 10)

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="训练" sub={`${plan.content.template} · 计划 v${plan.version}`}
        right={
          <button className="btn-sm btn border border-line bg-surface font-medium"
                  onClick={() => navigate('/training/edit')}>
            <Pencil size={14} /> 编辑计划
          </button>
        } />

      {offlineMode && (
        <Notice>当前离线：显示最近一次加载的计划；训练记录会暂存本机，恢复网络自动同步。</Notice>
      )}
      {plan.fenced && (
        <div className="flex items-start gap-2.5 rounded-2xl border-2 border-red-300 bg-red-50
                        p-3.5 text-sm font-medium leading-relaxed text-red-700">
          <TriangleAlert size={18} className="mt-0.5 shrink-0" />
          计划已隔离，以下内容仅作历史参考；去
          <Link to="/coach" className="font-semibold underline underline-offset-2">AI 教练</Link>
          处理安全记录并确认重排。
        </div>
      )}
      {deloadActive && (
        <Notice tone="amber">
          卸载周进行中（至 {deload!.until.slice(5)}）：重量按 {Math.round(deload!.factor * 100)}% 执行。
        </Notice>
      )}

      {/* 训练日切换 */}
      <div className="-mx-4 mb-3 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0">
        {plan.content.schedule.map((d) => (
          <button key={d.day}
                  onClick={() => setSelected(d.day)}
                  className={`flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-xl border px-4
                              text-sm font-medium transition-colors ${
                                d.day === activeDay
                                  ? 'border-night bg-night text-white'
                                  : 'border-line bg-surface text-muted hover:border-lineStrong hover:text-ink'}`}>
            {d.day}
            {d.day === weekday && (
              <span className={`size-1.5 rounded-full ${d.day === activeDay ? 'bg-accent' : 'bg-accent-deep'}`}
                    title="今天" />
            )}
          </button>
        ))}
        <button onClick={() => navigate('/workout/free')}
                className={`flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-xl border border-dashed
                            border-lineStrong px-4 text-sm font-medium text-muted transition-colors
                            hover:border-accent-deep/40 hover:text-ink`}>
          <Plus size={14} /> 自由训练
        </button>
      </div>

      {/* 选中训练日的动作列表（封面 + 名称 + 组数/次数/重量） */}
      {active && (
        <div className="card !p-0 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <h2 className="text-[17px] font-bold">{active.day} · {active.focus}</h2>
              <p className="mt-0.5 text-xs text-muted">
                {active.exercises.length} 个动作
                {active.estimated_minutes ? ` · 约 ${active.estimated_minutes} 分钟` : ''}
              </p>
            </div>
            {!plan.fenced && (
              <button className="btn-primary shrink-0"
                      onClick={() => navigate(`/workout/${encodeURIComponent(active.day)}`)}>
                <Play size={16} /> 开始
              </button>
            )}
          </div>
          <ul className="rows">
            {active.exercises.map((ex, i) => (
              <li key={i}>
                <div className="flex items-center gap-3 px-4 py-3">
                  <ExerciseCover uid={uid} exerciseId={ex.exercise_id} name={ex.name}
                                 className="size-14 shrink-0 rounded-xl" iconSize={20} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15px] font-medium">
                      {ex.name}
                      {ex.exercise_id && (
                        <Link to={`/explore/${encodeURIComponent(ex.exercise_id)}`}
                              className="ml-1.5 align-middle text-accent-deep hover:underline"
                              aria-label={`查看 ${ex.name} 教学`}>
                          <ChevronRight size={14} className="inline" />
                        </Link>
                      )}
                    </p>
                    {(ex.note || ex.why) && (
                      <p className="mt-0.5 truncate text-xs text-muted">{ex.note || ex.why}</p>
                    )}
                  </div>
                  <div className="nums shrink-0 text-right text-sm">
                    <p className="font-semibold">{ex.sets} 组 × {ex.reps} 次</p>
                    {ex.weight_kg != null && <p className="text-xs text-muted">{ex.weight_kg} kg</p>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {plan.fenced && (
            <p className="border-t border-line bg-red-50/60 px-4 py-3 text-xs leading-relaxed text-red-600">
              计划已隔离：旧动作安排暂不能执行（历史与实际活动记录不受影响）。
            </p>
          )}
        </div>
      )}

      {/* 训练模板（M6.4-A：可复用；与当前计划独立） */}
      <Card title="训练模板" className="mt-4"
            sub="从自由训练「存为模板」而来；从模板开始不影响当前计划"
            right={
              <div className="flex gap-1.5">
                <label className="btn-sm btn cursor-pointer border border-line bg-surface">
                  导入
                  <input type="file" accept="application/json" className="hidden"
                         onChange={async (e) => {
                           const f = e.target.files?.[0]
                           if (!f) return
                           try {
                             const list = JSON.parse(await f.text()) as TrainingTemplate[]
                             for (const t of Array.isArray(list) ? list : []) {
                               if (!t?.name || !Array.isArray(t.entries)) continue
                               await api.saveTrainingTemplate(uid, {
                                 name: `${t.name}`, entries: t.entries, note: t.note })
                             }
                             loadTemplates()
                           } catch { /* 坏文件忽略 */ }
                         }} />
                </label>
                <button className="btn-sm btn border border-line bg-surface"
                        onClick={() => {
                          const blob = new Blob([JSON.stringify(templates || [], null, 2)],
                                                { type: 'application/json' })
                          const a = document.createElement('a')
                          a.href = URL.createObjectURL(blob)
                          a.download = `fitness-coach-templates-${Date.now()}.json`
                          a.click(); URL.revokeObjectURL(a.href)
                        }}>
                  导出
                </button>
              </div>
            }>
        {!templates || templates.length === 0 ? (
          <p className="text-xs leading-relaxed text-muted">
            还没有模板。开始一次自由训练后，用「存为训练模板」把它保存下来，下次一键开始。
          </p>
        ) : (
          <ul className="rows">
            {templates.map((t) => (
              <li key={t.id} className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{t.name}</p>
                  <p className="nums text-xs text-muted">
                    {t.entries.length} 个动作{t.updated_at ? ` · ${t.updated_at.slice(0, 10)}` : ''}
                  </p>
                </div>
                <button className="btn-sm btn shrink-0 bg-night text-white"
                        onClick={() => navigate(`/workout/template/${t.id}`)}>
                  开始
                </button>
                <button className="btn-sm btn shrink-0 border border-line bg-surface text-muted"
                        onClick={async () => {
                          try {
                            await api.deleteTrainingTemplate(uid, t.id)
                            loadTemplates()
                          } catch { /* 已删除 */ }
                        }} aria-label={`删除模板 ${t.name}`}>
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 其他训练日快速入口 */}
      <Card title="计划备注" className="mt-4">
        <ul className="list-disc space-y-1 pl-4 text-[13px] leading-relaxed text-muted">
          {plan.content.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      </Card>

      {/* 计划版本历史 */}
      <Card title={<span className="flex items-center gap-1.5"><HistoryIcon size={15} /> 计划版本历史</span>}
            className="mt-4"
            right={<PlainButton onClick={() => setShowVersions((v) => !v)}>
              {showVersions ? '收起' : `展开（${versions?.length ?? '…'}）`}
            </PlainButton>}>
        {showVersions && (
          <ul className="space-y-2">
            {(versions || []).map((v) => (
              <li key={v.id} className="rounded-xl bg-canvas p-3 text-xs leading-relaxed">
                <div className="flex items-center justify-between gap-2">
                  <p>
                    <b className="nums">v{v.version}</b> · {v.action || '生成'}
                    {v.active && <Tag tone="brand" className="ml-1.5">当前</Tag>}
                  </p>
                  <span className="shrink-0 text-faint">{v.at?.slice(0, 10)}</span>
                </div>
                <p className="mt-0.5 text-muted">{v.reason || v.template}</p>
                {!v.active && (
                  <button className="mt-1.5 font-medium text-accent-deep hover:underline"
                          onClick={() => {
                            setRestoreNote('')
                            api.restorePlanVersion(uid, v.version, `网页恢复计划 v${v.version}`)
                              .then((r) => {
                                setRestoreNote(`已恢复 v${v.version} 为 v${r.plan_version}`)
                                api.plan(uid).then(setPlan)
                                loadVersions()
                              })
                              .catch((e) => setRestoreNote(e.message))
                          }}>恢复此版本</button>
                )}
              </li>
            ))}
          </ul>
        )}
        {restoreNote && <p className="mt-2 text-center text-xs text-accent-deep">{restoreNote}</p>}
      </Card>

      <div className="mt-4 grid grid-cols-2 gap-3">
        <Button variant="ghost" onClick={() => navigate('/training/edit')}>
          <Pencil size={15} /> 编辑计划
        </Button>
        <Link to="/history" className="btn-ghost">
          <CalendarRange size={15} /> 训练历史
        </Link>
      </div>
    </div>
  )
}
