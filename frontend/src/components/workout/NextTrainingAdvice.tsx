// P5-C2：训练科学顾问 · 下一次训练建议面板。
// 打开时实时拉取确定性候选（不依赖前端缓存）；AI 解释按需请求
// （TrainingScienceAgent，next-training-review）；仅本次采用走
// store.applySessionTarget；长期修改走统一 ChangeProposal 确认协议。
import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, FlaskConical, ShieldCheck, Sparkles } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, Empty, ErrorBox, Notice, Sheet, Spinner, Tag } from '../Bits'
import { PanelDataStatus } from './ProgressionEvidence'
import ProgressionOptionCard from './ProgressionOptionCard'
import { compatibleTargetPatch, useApp } from '../../store'
import type { SessionEntry } from '../../store'
import type { ExpertInsight, ProgressionPerformance,
              ProgressionResult } from '../../types'

export interface PlanAdviceContext {
  planId?: number | null
  planVersion?: number | null
  day?: string | null
  index?: number | null
  plannedExerciseId?: string | null
  baseVersion?: Record<string, unknown>
}

function currentPrescriptionLines(prescription: Record<string, unknown>): string {
  const parts: string[] = []
  if (prescription.sets != null) parts.push(`${prescription.sets} 组`)
  if (prescription.reps != null) parts.push(`${prescription.reps} 次`)
  if (prescription.weight_kg != null) parts.push(`${prescription.weight_kg} kg`)
  return parts.join(' × ') || '—'
}

function optionDiffLines(option: ProgressionResult['options'][number],
                         prescription: Record<string, unknown>): string[] {
  const t = option.proposed_targets || {}
  const lines: string[] = []
  if (t.sets != null && String(t.sets) !== String(prescription.sets ?? '')) {
    lines.push(`组数 ${prescription.sets ?? '—'} → ${t.sets}`)
  }
  if (t.reps != null && String(t.reps) !== String(prescription.reps ?? '')) {
    lines.push(`次数 ${prescription.reps ?? '—'} → ${t.reps}`)
  }
  if (t.weight_kg != null
      && Number(t.weight_kg) !== Number(prescription.weight_kg ?? 0)) {
    lines.push(`负重 ${prescription.weight_kg ?? '—'} → ${t.weight_kg} kg`)
  }
  return lines
}

function performanceText(perf: ProgressionPerformance): string {
  if (perf.interval_planned_rounds) {
    return `HIIT 完成 ${perf.interval_completed_rounds ?? 0}/${perf.interval_planned_rounds} 轮`
      + `（跳过 ${perf.interval_skipped_rounds ?? 0}）`
      + ` · 工作 ${perf.interval_work_seconds ?? 0}s · 休息 ${perf.interval_rest_seconds ?? 0}s`
      + (perf.interval_ended_early ? ' · 提前结束' : '')
  }
  if (perf.steady_cardio_seconds) {
    return `持续有氧 ${perf.steady_cardio_seconds}s`
      + (perf.steady_cardio_distance_m ? ` · ${perf.steady_cardio_distance_m}m` : '')
      + (perf.pace_sec_per_km ? ` · 配速 ${perf.pace_sec_per_km}s/km` : '（未记录距离）')
  }
  const sets = perf.working_sets ?? 0
  const reps = (perf.rep_values || []).join(' / ')
  const best = perf.best_set
  let text = `${sets} 组正式组`
  if (reps) text += ` · 次数 ${reps}`
  if (best?.weight_kg != null) text += ` · 最佳 ${best.weight_kg}kg×${best.reps ?? '—'}`
  if (perf.best_e1rm) text += ` · e1RM（估算）${perf.best_e1rm}`
  return text || '—'
}

function insightStatusText(status: string): string {
  return ({ ready: '有效', viewed: '已读', dismissed: '已忽略',
            expired: '已过期', invalidated: '已失效' } as Record<string, string>)[status]
    || status
}

function confidenceText(confidence: string): string {
  return ({ high: '高', medium: '中', low: '低' } as Record<string, string>)[confidence]
    || confidence
}

export default function NextTrainingAdvice({ uid, entry, entryIdx, planContext,
                                            onClose }: {
  uid: string
  entry: SessionEntry
  entryIdx: number
  planContext?: PlanAdviceContext
  onClose: () => void
}) {
  const displayName = entry.replaced_with || entry.name
  const exerciseId = entry.replace_exercise_id || entry.exercise_id
  const [result, setResult] = useState<ProgressionResult | null>(null)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [proposalId, setProposalId] = useState('')
  const [proposalStatus, setProposalStatus] = useState('')
  const [trialStarted, setTrialStarted] = useState<number | null>(null)
  const [insight, setInsight] = useState<ExpertInsight | null>(null)
  const [insightOpen, setInsightOpen] = useState(false)

  const draftMethod = useApp(
    (s) => s.session?.drafts?.[entryIdx]?.method)
  const appliedOptionId = useApp(
    (s) => s.session?.appliedTargets?.[entryIdx]?.optionId)
  const applySessionTarget = useApp((s) => s.applySessionTarget)
  const revertSessionTarget = useApp((s) => s.revertSessionTarget)

  const load = useCallback(() => {
    setError('')
    return api.trainingProgression(uid, exerciseId || '', {
      planId: planContext?.planId ?? null,
      planVersion: planContext?.planVersion ?? null,
      plannedDay: planContext?.day ?? null,
      index: planContext?.index ?? null,
      plannedExerciseId: planContext?.plannedExerciseId ?? null,
    }).then((r) => {
      setResult(r)
      setSelectedId((cur) =>
        cur && r.options.some((o) => o.option_id === cur)
          ? cur : r.options[0]?.option_id || '')
      return r
    }).catch((e: ApiError) => { setError(e.message) })
  }, [uid, exerciseId, planContext])

  useEffect(() => { load() }, [load])

  // 已有有效洞察：取全文供"专业解释"展开；失效洞察只显示状态与原因
  useEffect(() => {
    const ref = result?.insight
    if (ref && (ref.status === 'ready' || ref.status === 'viewed')) {
      api.expertInsight(uid, ref.id).then(setInsight).catch(() => {})
    } else {
      setInsight(null)
    }
  }, [result?.insight, uid])

  const options = result?.options || []
  const selected = options.find((o) => o.option_id === selectedId)
  const context = result?.context
  const compat = selected && context !== undefined
    ? compatibleTargetPatch(entry, selected.proposed_targets || {}, draftMethod)
    : null
  const canApply = !!compat && Object.keys(compat.patch).length > 0
  const canPropose = !!selected?.plan_proposal && !!planContext
  const canTrial = !!selected
    && Object.keys(selected.proposed_targets || {}).length > 0

  const applyForThisSession = () => {
    if (!selected) return
    const outcome = applySessionTarget(entryIdx,
                                       selected.proposed_targets || {},
                                       selected.option_id)
    if (outcome.applied) {
      setNotice('已按候选调整本次目标（仅本次有效，不影响长期计划；'
        + '已完成组、组法、超级组与计时器均未改动；可在动作卡或此处撤销）')
    } else {
      setNotice(`该候选与当前动作结构不兼容`
        + `（${outcome.incompatible.join('、')}），只能查看方向`)
    }
  }

  const proposeLongTerm = async () => {
    if (!selected || !planContext) return
    setBusy('plan'); setNotice(''); setError('')
    try {
      // 服务端按当前有效候选构造提案操作（不信任前端提交的目标数值）
      const staged = await api.adoptProgressionCandidate(uid, exerciseId || '', {
        option_id: selected.option_id,
        plan_id: planContext.planId, plan_version: planContext.planVersion,
        planned_day: planContext.day, index: planContext.index,
        planned_exercise_id: planContext.plannedExerciseId,
      })
      setProposalId(staged.proposal_id)
      setProposalStatus(staged.status)
      setNotice(staged.note || '已创建待确认修改提案；确认前长期计划保持不变')
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const startTrial = async () => {
    if (!selected) return
    setBusy('trial'); setNotice(''); setError('')
    try {
      const out = await api.startProgressionTrial(uid, exerciseId || '', {
        option_id: selected.option_id,
        plan_id: planContext?.planId, plan_version: planContext?.planVersion,
        planned_day: planContext?.day, index: planContext?.index,
        planned_exercise_id: planContext?.plannedExerciseId,
      })
      setTrialStarted(out.trial.id)
      setNotice(`个人尝试 #${out.trial.id} 已开始（${out.trial.stop_rule}）；`
        + '照常训练并记录，到「我的 → 个人尝试」复盘')
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const confirmLongTerm = async () => {
    if (!proposalId) return
    setBusy('confirm'); setError('')
    try {
      // 语义门要求明确的肯定表述：不回填候选标题（可能含"考虑"等模糊词）
      const done = await api.confirmChange(
        uid, proposalId, '确认采用：把这条长期修改落实到计划')
      setProposalStatus(done.status)
      setNotice(done.status === 'applied'
        ? '长期计划已更新为新版本；本次训练目标未自动改动'
        : '提案未生效，长期计划保持不变')
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const ignoreAdvice = async () => {
    const ref = result?.insight
    if (ref && (ref.status === 'ready' || ref.status === 'viewed')) {
      await api.dismissInsight(uid, ref.id).catch(() => {})
    }
    onClose()
  }

  const requestExplanation = async () => {
    setBusy('insight'); setNotice(''); setError('')
    try {
      const out = await api.requestAnalysis(uid, 'training_science', {
        exercise_id: exerciseId,
        ...(planContext ? {
          plan_id: planContext.planId, plan_version: planContext.planVersion,
          planned_day: planContext.day, index: planContext.index,
          planned_exercise_id: planContext.plannedExerciseId,
        } : {}),
      }, 'next-training-review')
      if (out.insight) {
        setInsight(out.insight)
        setInsightOpen(true)
        api.markInsightViewed(uid, out.insight.id).catch(() => {})
        load()  // 刷新面板上的洞察状态徽标
      } else {
        setNotice(`专业解释生成失败：${out.error || '未知原因'}`)
      }
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const regenerateExplanation = async () => {
    if (!insight) return
    setBusy('insight'); setError('')
    try {
      const out = await api.regenerateInsight(uid, insight.id)
      if (out.insight) setInsight(out.insight)
      load()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const perf = context?.last_actual_performance

  return (
    <Sheet open onClose={onClose} title={`训练科学顾问 · 下一次${displayName}`} wide>
      {error && <ErrorBox message={error} />}
      {!result && !error && <Spinner label="正在读取真实记录与当前计划…" />}

      {result && context && (
        <div className="space-y-3">
          {/* 最近表现（仅真实记录） */}
          <section className="rounded-xl bg-canvas p-3">
            <p className="text-xs font-semibold text-ink">
              上次实际完成{perf?.date ? ` · ${perf.date}` : ''}
            </p>
            <p className="nums mt-1 text-sm leading-relaxed">
              {perf ? performanceText(perf) : '还没有该动作的训练记录'}
            </p>
            <p className="nums mt-1 text-2xs text-muted">
              当前目标：{currentPrescriptionLines(context.current_prescription)}
              {context.plan_prescription_applies ? ''
                : '（计划处方不适用于当前上下文）'}
            </p>
          </section>

          {/* 数据状态 / 恢复事实 / 限制 */}
          <section className="rounded-xl border border-line p-3">
            <p className="text-xs font-semibold text-ink">数据状态与限制</p>
            <div className="mt-1.5">
              <PanelDataStatus context={context}
                               blockedReasons={result.blocked_reasons} />
            </div>
          </section>

          {/* 候选方案 */}
          {result.recommendations_allowed && options.length > 0 && (
            <section>
              <p className="text-xs font-semibold text-ink">候选方案</p>
              <p className="mt-0.5 text-2xs text-faint">{result.caliber}</p>
              <div role="radiogroup" aria-label="候选方案" className="mt-2 space-y-2">
                {options.map((o, i) => (
                  <ProgressionOptionCard key={o.option_id} option={o}
                    index={i} context={context}
                    selected={selectedId === o.option_id}
                    onSelect={() => setSelectedId(o.option_id)} />
                ))}
              </div>
            </section>
          )}
          {result.recommendations_allowed && options.length === 0 && (
            <Empty title="暂无可生成的候选">
              数据不足或该记录类型暂无适用的确定性规则；先按当前安排训练并记录，
              不会伪造增长趋势。
            </Empty>
          )}

          {/* 仅本次采用状态提示 */}
          {appliedOptionId && (
            <Notice tone="brand">
              本次目标已按候选调整（仅本次有效，不影响长期计划；已完成组未改动）。
            </Notice>
          )}
          {notice && (
            <Notice tone={proposalStatus === 'applied' ? 'brand' : 'amber'}>
              {notice}
            </Notice>
          )}

          {/* 长期提案差异 + 确认（确认前计划不变） */}
          {proposalId && proposalStatus === 'pending' && selected && context && (
            <section className="rounded-xl border border-amber-300 bg-amber-50 p-3">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-800">
                <AlertTriangle size={13} /> 待确认修改提案（长期计划当前版本未变）
              </p>
              <ul className="nums mt-1.5 space-y-0.5 text-xs text-amber-900">
                {optionDiffLines(selected, context.current_prescription)
                  .map((line) => <li key={line}>· {line}</li>)}
                {optionDiffLines(selected, context.current_prescription).length === 0
                  && <li>· 无实际差异</li>}
              </ul>
              <p className="mt-1.5 text-2xs leading-relaxed text-amber-800">
                确认时服务端会重新校验计划版本与安全状态；若确认前计划已被
                其他修改更新，该提案会被拒绝。
              </p>
              <Button className="btn-sm mt-2" disabled={busy === 'confirm'}
                      onClick={confirmLongTerm}>
                确认长期计划修改
              </Button>
            </section>
          )}

          {/* AI 解释（按需，TrainingScienceAgent） */}
          <section className="rounded-xl border border-line p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                <Sparkles size={13} className="text-accent-deep" /> 专业解释
                {result.insight && (
                  <Tag tone={result.insight.status === 'ready'
                    || result.insight.status === 'viewed' ? 'green' : 'neutral'}>
                    {insightStatusText(result.insight.status)}
                  </Tag>
                )}
              </p>
              {result.insight && result.insight.status !== 'ready'
                && result.insight.status !== 'viewed' && (
                <button className="text-2xs text-muted underline underline-offset-2"
                        onClick={() => (insight
                          ? regenerateExplanation()
                          : requestExplanation())}
                        disabled={busy === 'insight'}>
                  重新分析
                </button>
              )}
            </div>
            {result.insight?.status_reason && (
              <p className="mt-1 text-2xs text-amber-700">
                {result.insight.status_reason}
              </p>
            )}
            {!insight && (
              <div className="mt-2">
                <Button variant="ghost" className="btn-sm"
                        disabled={busy === 'insight'}
                        onClick={requestExplanation}>
                  请求专业解释（AI 解读候选与依据）
                </Button>
              </div>
            )}
            {insight && (
              <div className="mt-2 space-y-2">
                <button className="btn-plain !px-0 text-xs"
                        aria-expanded={insightOpen}
                        onClick={() => {
                          setInsightOpen(!insightOpen)
                          if (!insightOpen && insight.status === 'ready') {
                            api.markInsightViewed(uid, insight.id).catch(() => {})
                          }
                        }}>
                  {insightOpen ? '收起解释' : '查看专业解释'}
                  <span className="ml-1.5 text-2xs text-faint">
                    置信度 {confidenceText(insight.confidence)}
                  </span>
                </button>
                {insightOpen && (
                  <div className="space-y-2 text-xs leading-relaxed text-muted">
                    <p className="text-ink">{insight.summary}</p>
                    {insight.findings.map((f) => (
                      <p key={f.finding_id}
                         className={f.evidence === 'unverified' ? 'text-faint' : ''}>
                        · {f.text}
                      </p>
                    ))}
                    {insight.limitations.map((line, i) => (
                      <p key={i} className="text-2xs text-faint">· {line}</p>
                    ))}
                    <p className="text-2xs text-faint">{insight.confidence_basis}</p>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* 动作条：仅本次采用 / 申请修改长期计划 / 个人尝试 / 忽略 */}
          <div className="flex flex-wrap gap-2 border-t border-line pt-3">
            <Button className="btn-sm flex-1" disabled={!canApply || busy !== ''}
                    onClick={applyForThisSession}>
              仅本次采用
            </Button>
            <Button variant="ghost" className="btn-sm flex-1"
                    disabled={!canPropose || busy !== ''
                      || proposalStatus === 'applied'}
                    onClick={proposeLongTerm}>
              <ShieldCheck size={14} /> 申请修改长期计划
            </Button>
            <Button variant="ghost" className="btn-sm"
                    disabled={!canTrial || busy !== '' || trialStarted != null}
                    onClick={startTrial}>
              <FlaskConical size={14} />
              {trialStarted ? `尝试 #${trialStarted} 进行中` : '开始个人尝试'}
            </Button>
            <Button variant="ghost" className="btn-sm" onClick={ignoreAdvice}>
              忽略
            </Button>
          </div>
          <div className="flex items-center justify-between gap-2">
            {selected && !canApply && options.length > 0 && (
              <p className="text-2xs leading-relaxed text-faint">
                {compat && compat.incompatible.length > 0
                  ? `所选候选的 ${compat.incompatible.join('、')} 字段不适用于当前动作结构，仅展示方向。`
                  : '所选候选只提供方向，没有可直接套用的目标字段。'}
              </p>
            )}
            {appliedOptionId && (
              <button className="btn-plain text-xs"
                      onClick={() => { revertSessionTarget(entryIdx) }}>
                撤销本次调整
              </button>
            )}
          </div>
        </div>
      )}
    </Sheet>
  )
}
