import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardPlus, MessageCircleHeart, ShieldAlert, Stethoscope } from 'lucide-react'
import { api, ApiError } from '../../api'
import {
  Button, Empty, ErrorBox, Input, PageHeader, Segmented, Sheet, Textarea,
} from '../../components/Bits'
import BodyMap, { parseSelection } from '../../components/rehab/BodyMap'
import { REGION_LABEL, SOURCE_LABEL, TRIAGE_TONE, regionText } from '../../lib/rehab'
import { useApp } from '../../store'
import type {
  CarePlan, SymptomEpisode, TriageResult, TrainingRestriction,
} from '../../types'

type Tab = 'overview' | 'restrictions' | 'care' | 'consult'

const TABS: { value: Tab; label: string }[] = [
  { value: 'overview', label: '不适记录' },
  { value: 'restrictions', label: '训练限制' },
  { value: 'care', label: '专业安排' },
  { value: 'consult', label: '咨询' },
]

/** 康复与伤痛风险顾问工作台（P3） */
export default function Rehabilitation() {
  const uid = useApp((s) => s.uid)
  const [tab, setTab] = useState<Tab>('overview')
  const [episodes, setEpisodes] = useState<SymptomEpisode[]>([])
  const [restrictions, setRestrictions] = useState<TrainingRestriction[]>([])
  const [plans, setPlans] = useState<CarePlan[]>([])
  const [reportOpen, setReportOpen] = useState(false)
  const [observeOpen, setObserveOpen] = useState<SymptomEpisode | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.symptomEpisodes(uid),
      api.restrictions(uid),
      api.carePlans(uid).catch(() => ({ plans: [] as CarePlan[] })),
    ]).then(([e, r, p]) => {
      setEpisodes(e.episodes); setRestrictions(r.restrictions); setPlans(p.plans)
    }).catch((err) => setError((err as ApiError).message))
  }, [uid])
  useEffect(load, [load])

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="康复与伤痛风险" sub="记录不适 · 安全分流 · 训练限制 · 专业安排跟踪"
        right={<span className="tag bg-accent-soft text-accent-deep">
          <Stethoscope size={13} /> 顾问
        </span>} />
      {/* 定位声明（必须醒目） */}
      <div className="mb-4 rounded-2xl border border-line bg-surface/70 p-3 text-xs leading-relaxed text-muted">
        本工作台是运动健康辅助工具：帮助你<b className="text-ink">记录不适、识别需要专业评估的情形、
        管理训练限制</b>。它<b className="text-ink">不提供疾病诊断、医学治疗或临床康复处方</b>；
        出现严重症状请立即就医。
      </div>
      <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      {tab === 'overview' && (
        <div className="space-y-4">
          <button className="btn-primary btn w-full" onClick={() => setReportOpen(true)}>
            <ClipboardPlus size={16} /> 记录身体不适
          </button>
          {episodes.length === 0 ? (
            <Empty icon={<Stethoscope size={22} />} title="还没有不适记录">
              在人体图上选择区域，30 秒完成一次记录；系统会立即做确定性安全分流
              （不依赖任何 AI 任务）。
            </Empty>
          ) : (
            <div className="space-y-3">
              {episodes.map((ep) => (
                <EpisodeCard key={ep.id} episode={ep}
                             onObserve={() => setObserveOpen(ep)} />
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'restrictions' && (
        <div className="space-y-3">
          <div className="rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
            多来源限制并存时<b className="text-ink">全部生效</b>；任何顾问/AI 只能收紧不能解除。
            专业人员给出的限制必须附<b className="text-ink">专业人员的解除说明</b>才能解除。
          </div>
          {restrictions.length === 0 ? (
            <p className="card text-sm text-muted">当前没有生效的训练限制。</p>
          ) : restrictions.map((r) => (
            <RestrictionCard key={r.id} restriction={r} onChanged={load} />
          ))}
        </div>
      )}

      {tab === 'care' && <CareSection plans={plans} onChanged={load} />}

      {tab === 'consult' && (
        <div className="card">
          <Link to="/experts/chat" className="flex items-center gap-3.5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
              <MessageCircleHeart size={21} className="text-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">向主教练提问</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                聊天是工作台的辅助；风险分流与限制始终以本页的确定性规则为准
              </p>
            </div>
          </Link>
        </div>
      )}

      {reportOpen && (
        <ReportSheet onClose={() => setReportOpen(false)} onSaved={load} />
      )}
      {observeOpen && (
        <ObserveSheet episode={observeOpen} onClose={() => setObserveOpen(null)}
                      onSaved={load} />
      )}
    </div>
  )
}

function EpisodeCard({ episode, onObserve }: {
  episode: SymptomEpisode; onObserve: () => void }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<SymptomEpisode | null>(null)
  const uid = useApp((s) => s.uid)
  const latest = episode.observations?.[episode.observations.length - 1]
  const triage = latest?.triage_result
  useEffect(() => {
    if (!open || detail) return
    api.symptomEpisode(uid, episode.id).then(setDetail).catch(() => {})
  }, [open, detail, uid, episode.id])
  const tone = triage ? TRIAGE_TONE[triage.action] : null
  return (
    <div className="card">
      <button type="button" className="w-full text-left" onClick={() => setOpen(!open)}>
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-[15px] font-semibold">
            {regionText(episode.body_region, episode.side)}
          </p>
          <span className="tag bg-ink/5 text-muted">起病 {episode.onset_at}</span>
          {episode.status !== 'active' && (
            <span className="tag bg-ink/5 text-faint">{episode.status === 'resolved' ? '已缓解' : '观察中'}</span>
          )}
          {tone && <span className={`tag border ${tone.cls}`}>{tone.label}</span>}
        </div>
        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-ink/80">
          {episode.description}
        </p>
        {triage && (
          <p className={`mt-1.5 rounded-lg border p-2 text-xs leading-relaxed ${tone!.cls}`}>
            {triage.message}
          </p>
        )}
      </button>
      {open && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-xs font-semibold text-muted">观察历史（{detail?.observations?.length ?? 0} 次）</p>
          <ul className="mt-1.5 space-y-1.5">
            {(detail?.observations ?? []).map((o) => (
              <li key={o.id} className="rounded-lg bg-canvas p-2.5 text-xs leading-relaxed">
                <span className="font-medium">{o.recorded_at.slice(0, 16).replace('T', ' ')}</span>
                {o.severity != null && <span className="ml-2">程度 {o.severity}/10</span>}
                {o.symptom_description && <p className="mt-0.5">{o.symptom_description}</p>}
                {o.functional_limitations.length > 0 && (
                  <p className="mt-0.5 text-muted">影响：{o.functional_limitations.join('、')}</p>
                )}
                {o.user_notes && <p className="mt-0.5 text-faint">{o.user_notes}</p>}
                {o.triage_result && (
                  <p className="mt-0.5 text-faint">分流：{TRIAGE_TONE[o.triage_result.action]?.label}
                    （{o.triage_result.rules_version}）</p>
                )}
              </li>
            ))}
          </ul>
          <button className="btn-soft btn mt-2 w-full text-xs" onClick={onObserve}>
            追加观察（程度/变化）
          </button>
        </div>
      )}
    </div>
  )
}

function RestrictionCard({ restriction, onChanged }: {
  restriction: TrainingRestriction; onChanged: () => void }) {
  const uid = useApp((s) => s.uid)
  const [lifting, setLifting] = useState(false)
  const [evidence, setEvidence] = useState('')
  const [error, setError] = useState('')
  const aff = restriction.affected_activities
  return (
    <div className="card border-l-4 border-l-amber-400">
      <div className="flex flex-wrap items-center gap-2">
        <ShieldAlert size={16} className="text-amber-600" />
        <span className="tag bg-ink/5 text-muted">
          {SOURCE_LABEL[restriction.source_type] ?? restriction.source_type}
        </span>
        <span className="text-xs text-faint">生效 {restriction.effective_at.slice(0, 10)}</span>
        {restriction.review_at && (
          <span className="tag bg-amber-50 text-amber-700">复核时点 {restriction.review_at}</span>
        )}
      </div>
      <p className="mt-1.5 text-[13px] font-medium leading-relaxed">
        {restriction.restriction_description}
      </p>
      <p className="mt-1 text-xs text-muted">
        覆盖：{[...(aff.regions || []).map((r) => REGION_LABEL[r] ?? r),
               ...(aff.movements || [])].join('、') || '—'}
      </p>
      <p className="mt-1 text-2xs leading-relaxed text-faint">依据：{restriction.source_evidence}</p>
      {lifting ? (
        <div className="mt-2 space-y-2">
          {restriction.source_type === 'professional' && (
            <p className="text-2xs leading-relaxed text-amber-700">
              该限制来自专业人员：解除必须录入<b>专业人员本人的说明</b>（如复诊结论原文），
              AI 与系统提示均不能解除。
            </p>
          )}
          <Textarea value={evidence} rows={2} onChange={(e) => setEvidence(e.target.value)}
                    placeholder="解除依据（你的原话或专业人员说明原文）" />
          {error && <ErrorBox message={error} />}
          <div className="flex gap-2">
            <Button className="text-xs" disabled={!evidence.trim()}
                    onClick={async () => {
                      setError('')
                      try {
                        await api.liftRestriction(uid, restriction.id, {
                          expected_revision: restriction.revision, lift_evidence: evidence })
                        onChanged()
                      } catch (e) { setError((e as ApiError).message) }
                    }}>
              确认解除（留痕）
            </Button>
            <Button variant="ghost" className="text-xs" onClick={() => setLifting(false)}>取消</Button>
          </div>
        </div>
      ) : (
        <button className="btn-ghost btn mt-2 w-full text-xs" onClick={() => setLifting(true)}>
          情况已变化？申请解除（需依据，全部留痕）
        </button>
      )}
    </div>
  )
}

function CareSection({ plans, onChanged }: { plans: CarePlan[]; onChanged: () => void }) {
  const uid = useApp((s) => s.uid)
  const [creating, setCreating] = useState(false)
  const today = new Date().toISOString().slice(0, 10)
  return (
    <div className="space-y-3">
      <div className="rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
        这里用于录入<b className="text-ink">合格专业人员已经给出的活动建议</b>，
        软件只做记录、提醒与执行统计，<b className="text-ink">不会自行提高强度、次数或难度</b>。
      </div>
      <button className="btn-soft btn w-full text-sm" onClick={() => setCreating(true)}>
        录入专业人员的安排
      </button>
      {plans.length === 0 ? (
        <p className="card text-sm text-muted">还没有录入专业安排。</p>
      ) : plans.map((p) => (
        <div key={p.id} className="card">
          <p className="text-[15px] font-semibold">{p.title}</p>
          <p className="mt-0.5 text-xs text-muted">来源：{p.professional_source}</p>
          {p.applicable_conditions && (
            <p className="mt-0.5 text-2xs text-faint">适用条件：{p.applicable_conditions}</p>
          )}
          <ul className="mt-2 space-y-2">
            {p.activities.map((a) => {
              const doneToday = a.logs?.some((l) => l.local_date === today)
              return (
                <li key={a.id} className="rounded-xl bg-canvas p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium">{a.name}</p>
                      {a.frequency && <p className="text-2xs text-muted">{a.frequency}</p>}
                    </div>
                    <button className={`btn text-xs ${doneToday ? 'btn-ghost text-emerald-700'
                                        : 'btn-soft'}`}
                            disabled={doneToday}
                            onClick={async () => {
                              await api.logCareActivity(uid, a.id, {
                                local_date: today, completed: true })
                              onChanged()
                            }}>
                      {doneToday ? '今日已执行✓' : '记今日执行'}
                    </button>
                  </div>
                  {a.logs && a.logs.length > 0 && (
                    <p className="mt-1 text-2xs text-faint">
                      近 {a.logs.length} 次记录 · 最近 {a.logs[0].local_date}
                      {a.logs[0].feedback ? ` · ${a.logs[0].feedback}` : ''}
                    </p>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      ))}
      {creating && (
        <CarePlanSheet onClose={() => setCreating(false)} onSaved={onChanged} />
      )}
    </div>
  )
}

function CarePlanSheet({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [title, setTitle] = useState('')
  const [source, setSource] = useState('')
  const [conditions, setConditions] = useState('')
  const [acts, setActs] = useState([{ name: '', frequency: '' }])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Sheet open title="录入专业人员的安排" onClose={onClose}>
      <label className="block"><span className="mb-1 block text-xs text-muted">安排名称 *</span>
        <Input value={title} onChange={(e) => setTitle(e.target.value)}
               placeholder="如：膝部活动度练习" /></label>
      <label className="mt-2 block"><span className="mb-1 block text-xs text-muted">
        专业人员来源说明 *（谁、何时给的）</span>
        <Input value={source} onChange={(e) => setSource(e.target.value)}
               placeholder="如：物理治疗师王（2026-10 面诊）" /></label>
      <label className="mt-2 block"><span className="mb-1 block text-xs text-muted">适用条件</span>
        <Input value={conditions} onChange={(e) => setConditions(e.target.value)} /></label>
      <p className="mt-3 text-xs font-semibold">活动清单</p>
      {acts.map((a, i) => (
        <div key={i} className="mt-1.5 flex gap-2">
          <Input className="flex-1" value={a.name} placeholder="活动名称"
                 onChange={(e) => setActs(acts.map((x, j) =>
                   j === i ? { ...x, name: e.target.value } : x))} />
          <Input className="w-36" value={a.frequency} placeholder="频率（按医嘱）"
                 onChange={(e) => setActs(acts.map((x, j) =>
                   j === i ? { ...x, frequency: e.target.value } : x))} />
        </div>
      ))}
      <button className="mt-1.5 text-xs font-medium text-accent-deep"
              onClick={() => setActs([...acts, { name: '', frequency: '' }])}>
        + 再加一项
      </button>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <Button className="mt-3" block disabled={busy || !title.trim() || !source.trim()}
              onClick={async () => {
                setBusy(true); setError('')
                try {
                  await api.createCarePlan(uid, {
                    title, professional_source: source,
                    applicable_conditions: conditions,
                    activities: acts.filter((a) => a.name.trim()) })
                  onSaved(); onClose()
                } catch (e) { setError((e as ApiError).message) }
                finally { setBusy(false) }
              }}>
        {busy ? '保存中…' : '保存安排'}
      </Button>
    </Sheet>
  )
}

/** 记录不适：人体图选区域 → 描述 → 实时分流预览 → 保存（同步分流） */
function ReportSheet({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [view, setView] = useState<'front' | 'back'>('front')
  const [selected, setSelected] = useState<string[]>([])
  const [onset, setOnset] = useState(new Date().toISOString().slice(0, 10))
  const [context, setContext] = useState('')
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState('')
  const [limitations, setLimitations] = useState('')
  const [professional, setProfessional] = useState(false)
  const [preview, setPreview] = useState<TriageResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // 实时分流预览（确定性规则，纯前端防抖 + 后端同源规则）
  useEffect(() => {
    if (!description.trim()) { setPreview(null); return }
    const t = setTimeout(() => {
      api.triagePreview({
        description, severity: severity ? Number(severity) : null,
        functional_limitations: limitations.split(/[，,、]/).map((s) => s.trim()).filter(Boolean),
        onset_at: onset, professional_evaluated: professional,
      }).then(setPreview).catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(t)
  }, [description, severity, limitations, onset, professional])

  async function save() {
    setBusy(true); setError('')
    const picks = parseSelection(selected)
    try {
      // 多区域：逐个创建事件（区域/侧别是事件的固有属性）
      for (const p of picks) {
        await api.reportSymptom(uid, {
          body_region: p.region, side: p.side === 'left' ? 'left' : 'right',
          onset_at: onset, onset_context: context, description,
          severity: severity ? Number(severity) : null,
          functional_limitations: limitations.split(/[，,、]/).map((s) => s.trim()).filter(Boolean),
          professional_evaluated: professional,
        }, `sym-${Date.now().toString(36)}-${p.region}-${p.side}`)
      }
      onSaved(); onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  const tone = preview ? TRIAGE_TONE[preview.action] : null
  return (
    <Sheet open title="记录身体不适" onClose={onClose} wide>
      <div className="grid gap-4 sm:grid-cols-[180px,1fr]">
        <div>
          <Segmented value={view} onChange={setView}
                     options={[{ value: 'front', label: '正面' }, { value: 'back', label: '背面' }]} />
          <BodyMap view={view} selected={selected}
                   onToggle={(key) => setSelected(selected.includes(key)
                     ? selected.filter((x) => x !== key) : [...selected, key])} />
          <p className="mt-1 text-center text-2xs text-faint">点击标记不适区域（可多选/分左右）</p>
          {selected.length > 0 && (
            <p className="mt-1 text-center text-xs font-medium">
              {parseSelection(selected).map((p) =>
                regionText(p.region, p.side)).join('、')}
            </p>
          )}
        </div>
        <div className="space-y-2.5">
          <div className="grid grid-cols-2 gap-2">
            <label><span className="mb-1 block text-xs text-muted">大致发生日期 *</span>
              <Input type="date" value={onset}
                     onChange={(e) => setOnset(e.target.value)} /></label>
            <label><span className="mb-1 block text-xs text-muted">自报程度 1-10（可选）</span>
              <Input inputMode="numeric" value={severity}
                     onChange={(e) => setSeverity(e.target.value)}
                     placeholder="不填=不确定" /></label>
          </div>
          <label className="block"><span className="mb-1 block text-xs text-muted">
            怎么发生的 / 与运动有关吗</span>
            <Input value={context} onChange={(e) => setContext(e.target.value)}
                   placeholder="如：周二加深蹲量后出现 / 逐渐出现 / 崴脚" /></label>
          <label className="block"><span className="mb-1 block text-xs text-muted">
            描述不适 *（何时痛、什么感觉）</span>
            <Textarea value={description} rows={3}
                      onChange={(e) => setDescription(e.target.value)}
                      placeholder="如：深蹲后膝盖外侧有点酸，上下楼没影响" /></label>
          <label className="block"><span className="mb-1 block text-xs text-muted">
            影响了哪些日常活动（可选，逗号分隔）</span>
            <Input value={limitations} onChange={(e) => setLimitations(e.target.value)}
                   placeholder="如：走路, 下楼" /></label>
          <label className="flex items-center gap-2 text-xs">
            <input type="checkbox" checked={professional}
                   onChange={(e) => setProfessional(e.target.checked)} />
            已经接受过专业评估（医生/物理治疗师）
          </label>
          {preview && tone && (
            <div className={`rounded-xl border p-3 text-xs leading-relaxed ${tone.cls}`}>
              <p className="font-semibold">安全分流预览 · {tone.label}</p>
              <p className="mt-1">{preview.message}</p>
              <p className="mt-1 text-2xs opacity-80">{preview.disclaimer} ·
                规则 {preview.rules_version}（{preview.review_status}）</p>
            </div>
          )}
          {error && <ErrorBox message={error} />}
          <Button block disabled={busy || !description.trim() || selected.length === 0}
                  onClick={save}>
            {busy ? '保存中…' : `保存记录${selected.length > 1 ? `（${selected.length} 个区域）` : ''}`}
          </Button>
          <p className="text-2xs leading-relaxed text-faint">
            保存时立即执行确定性安全分流；命中警示情形会提示就医并自动收紧相关训练限制。
            自报程度不用于推断损伤严重程度。
          </p>
        </div>
      </div>
    </Sheet>
  )
}

function ObserveSheet({ episode, onClose, onSaved }: {
  episode: SymptomEpisode; onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [severity, setSeverity] = useState('')
  const [desc, setDesc] = useState('')
  const [notes, setNotes] = useState('')
  const [limitations, setLimitations] = useState('')
  const [preview, setPreview] = useState<TriageResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!desc.trim() && !notes.trim() && !severity) { setPreview(null); return }
    const t = setTimeout(() => {
      api.triagePreview({
        description: desc || notes, severity: severity ? Number(severity) : null,
        functional_limitations: limitations.split(/[，,、]/).map((s) => s.trim()).filter(Boolean),
        onset_at: episode.onset_at,
      }).then(setPreview).catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(t)
  }, [desc, notes, severity, limitations, episode.onset_at])

  return (
    <Sheet open title={`追加观察 · ${regionText(episode.body_region, episode.side)}`}
           onClose={onClose}>
      <p className="text-2xs leading-relaxed text-muted">
        记录这次的变化（不覆盖历史）；分流按本次新报告的内容重新评估。
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label><span className="mb-1 block text-xs text-muted">程度 1-10（可选）</span>
          <Input inputMode="numeric" value={severity}
                 onChange={(e) => setSeverity(e.target.value)} /></label>
        <label><span className="mb-1 block text-xs text-muted">功能影响（可选）</span>
          <Input value={limitations} onChange={(e) => setLimitations(e.target.value)}
                 placeholder="如：下楼" /></label>
      </div>
      <label className="mt-2 block"><span className="mb-1 block text-xs text-muted">这次的情况</span>
        <Textarea value={desc} rows={2} onChange={(e) => setDesc(e.target.value)}
                  placeholder="如：比昨天好一些，走路没影响" /></label>
      <label className="mt-2 block"><span className="mb-1 block text-xs text-muted">备注</span>
        <Input value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      {preview && (
        <div className={`mt-2 rounded-xl border p-2.5 text-xs leading-relaxed ${
          TRIAGE_TONE[preview.action].cls}`}>
          <b>{TRIAGE_TONE[preview.action].label}：</b>{preview.message}
        </div>
      )}
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <Button className="mt-3" block disabled={busy || (!desc.trim() && !notes.trim() && !severity)}
              onClick={async () => {
                setBusy(true); setError('')
                try {
                  await api.observeSymptom(uid, episode.id, {
                    severity: severity ? Number(severity) : null,
                    symptom_description: desc, user_notes: notes,
                    functional_limitations: limitations.split(/[，,、]/)
                      .map((s) => s.trim()).filter(Boolean) })
                  onSaved(); onClose()
                } catch (e) { setError((e as ApiError).message) }
                finally { setBusy(false) }
              }}>
        {busy ? '保存中…' : '保存观察'}
      </Button>
    </Sheet>
  )
}
