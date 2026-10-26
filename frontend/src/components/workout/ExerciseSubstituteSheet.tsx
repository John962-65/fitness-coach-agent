import { useEffect, useState } from 'react'
import { AlertTriangle, Repeat2, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, Empty, ErrorBox, Sheet, Spinner } from '../Bits'
import { replaceByIndex } from '../../lib/protocol'
import type { SessionEntry } from '../../store'
import type { SubstituteCandidate, SubstituteResult } from '../../types'

export interface PlanReplacementContext {
  day: string
  index: number
  baseVersion: Record<string, unknown>
}

export default function ExerciseSubstituteSheet({
  uid, entry, locationId, planContext, onClose, onSessionReplace,
}: {
  uid: string
  entry: SessionEntry
  locationId?: number
  planContext?: PlanReplacementContext
  onClose: () => void
  onSessionReplace: (candidate: SubstituteCandidate) => void
}) {
  const sourceId = entry.replaced_from_id || entry.exercise_id
  const [result, setResult] = useState<SubstituteResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [proposalId, setProposalId] = useState('')
  const [proposalState, setProposalState] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    api.exerciseSubstitutes(uid, sourceId, locationId)
      .then(setResult)
      .catch((e: ApiError) => setError(e.message))
  }, [uid, sourceId, locationId])

  const useSession = async (candidate: SubstituteCandidate) => {
    setBusy(candidate.id); setError('')
    try {
      await api.validateSubstitution(uid, {
        source_exercise_id: sourceId,
        target_exercise_id: candidate.id,
        location_id: locationId,
      })
      onSessionReplace(candidate)
      onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const proposeLongTerm = async (candidate: SubstituteCandidate) => {
    if (!planContext) return
    setBusy(`plan-${candidate.id}`); setError(''); setNotice('')
    try {
      const staged = await api.stageChange(
        uid, 'plan',
        [replaceByIndex(planContext.day, planContext.index, candidate.id)],
        `训练中替换：${entry.replaced_with || entry.name} → ${candidate.name}`,
        planContext.baseVersion)
      setProposalId(staged.proposal_id)
      setProposalState(staged.status)
      setNotice(`已创建待确认修改：${entry.replaced_with || entry.name} → ${candidate.name}`)
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  const confirmLongTerm = async () => {
    if (!proposalId) return
    setBusy('confirm'); setError('')
    try {
      const result = await api.confirmChange(
        uid, proposalId, `确认长期计划替换：${entry.replaced_with || entry.name}`)
      setProposalState(result.status)
      setNotice(result.status === 'applied'
        ? '长期计划已确认更新；本次训练动作未被自动修改'
        : '提案仍在待确认状态，长期计划尚未改变')
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  return (
    <Sheet open onClose={onClose} title="动作替代候选" wide>
      <div className="mb-3 rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
        原动作：<b className="text-ink">{entry.replaced_with || entry.name}</b>
        {result && ` · 当前地点：${result.location.name}`}
        <p className="mt-1">候选按动作模式、目标肌群、器械、水平和安全限制确定性筛选，
          不代表与原动作等价。</p>
      </div>
      {error && <ErrorBox message={error} />}
      {notice && (
        <div className="mb-3 rounded-xl bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
          <p className="flex items-start gap-1.5">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {notice}
          </p>
          {proposalId && proposalState === 'pending' && (
            <Button className="mt-2 text-xs" disabled={busy === 'confirm'}
                    onClick={confirmLongTerm}>
              确认长期计划修改
            </Button>
          )}
        </div>
      )}
      {!result && !error && <Spinner />}
      {result && result.candidates.length === 0 && (
        <Empty title="没有通过筛选的候选">
          当前器械或安全限制下暂无可替代动作；不会自动删除或改动原动作。
        </Empty>
      )}
      <div className="space-y-2.5">
        {result?.candidates.map((candidate) => (
          <div key={candidate.id} className="rounded-xl border border-line bg-surface p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{candidate.name}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {candidate.pattern} · {candidate.primary.join('、') || '—'} ·
                  {' '}{candidate.equipment_names.join('、') || '自重'}
                </p>
              </div>
              <span className="tag shrink-0 bg-accent-soft text-accent-deep">
                匹配 {candidate.score}
              </span>
            </div>
            <ul className="mt-2 space-y-0.5 text-2xs leading-relaxed text-muted">
              {candidate.differences.map((line) => <li key={line}>· {line}</li>)}
            </ul>
            {candidate.reasons.length > 0 && (
              <p className="mt-1.5 text-2xs text-accent-deep">
                筛选依据：{candidate.reasons.join('、')}
              </p>
            )}
            <div className="mt-2.5 flex flex-wrap gap-2">
              <Button className="btn-sm" disabled={!!busy}
                      onClick={() => useSession(candidate)}>
                <Repeat2 size={14} /> 仅本次训练替换
              </Button>
              {planContext && (
                <Button variant="ghost" className="btn-sm" disabled={!!busy || !!proposalId}
                        onClick={() => proposeLongTerm(candidate)}>
                  <ShieldCheck size={14} /> 提交长期计划修改
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
      {result && (
        <p className="mt-3 text-2xs leading-relaxed text-faint">
          {result.disclaimer}
          {' '}已排除：器械/地点 {result.excluded.equipment_or_location}，
          记录口径/水平 {result.excluded.measurement_or_level}，
          安全限制 {result.excluded.safety}，
          目标不相关 {result.excluded.unrelated ?? 0}，
          未审核 {result.excluded.unapproved}。
        </p>
      )}
    </Sheet>
  )
}
