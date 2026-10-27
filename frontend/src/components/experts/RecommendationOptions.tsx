import { useState } from 'react'
import { ClipboardCheck, ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../../api'
import { opSummary } from '../../pages/Coach'
import { CONFIDENCE } from '../../lib/experts'
import { ExpertInsight } from '../../types'
import { useApp } from '../../store'

interface Staged {
  proposalId: string
  optionId: string
  operations: Record<string, unknown>[]
}

/** 方案呈现与用户决策：取舍并列、不自动裁决；
 * 计划修改必须经统一修改协议（stage → 用户明确确认 → 生效）。 */
export default function RecommendationOptions({ insight, onChanged }:
  { insight: ExpertInsight; onChanged: () => void }) {
  const uid = useApp((s) => s.uid)
  const [staged, setStaged] = useState<Staged | null>(null)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [result, setResult] = useState('')
  const [error, setError] = useState('')

  const actionable = insight.status === 'ready' || insight.status === 'viewed'
  const conf = CONFIDENCE[insight.confidence]

  async function stage(optionId: string) {
    setBusy(optionId); setError(''); setResult('')
    try {
      const resp = await api.stageInsightProposal(uid, insight.id, optionId)
      setStaged({ proposalId: resp.proposal.proposal_id, optionId,
                 operations: insight.options.find((o) => o.option_id === optionId)
                   ?.proposal_hint?.operations ?? [] })
      setMessage('')
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  async function decide() {
    if (!staged) return
    setBusy('confirm'); setError(''); setResult('')
    try {
      const resp = await api.confirmChange(
        uid, staged.proposalId, `${message}（提案 ${staged.proposalId}）`)
      if (resp.decision === 'unclear') {
        setResult('你的表述还不够明确，提案仍在等待确认。可以输入「确认」或「不同意」。')
      } else {
        setResult(resp.status === 'applied' ? '已按你的确认生效，计划已更新。' : '已按你的意思拒绝，计划未变。')
        setStaged(null); setMessage(''); onChanged()
      }
    } catch (e) {
      setError((e as ApiError).message + ((e as ApiError).details.length
        ? `（${(e as ApiError).details.join('；')}）` : ''))
    } finally { setBusy('') }
  }

  async function dismiss() {
    setBusy('dismiss'); setError('')
    try {
      await api.dismissInsight(uid, insight.id)
      setResult('已忽略这条分析（历史保留，随时可重新分析）。')
      onChanged()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  async function regenerate() {
    setBusy('regen'); setError(''); setResult('')
    try {
      await api.regenerateInsight(uid, insight.id)
      setResult('已用最新数据重新分析。')
      onChanged()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-accent-deep" />
        <span>
          方案由规则从你的训练事实生成，置信度：
          <b className="text-ink">{conf?.label ?? insight.confidence}</b>（{conf?.note}）。
          每个方案列出收益、代价与适用条件——<b className="text-ink">由你选择</b>；
          需要改计划的一律走修改提案，你确认后才生效。
        </span>
      </div>

      {insight.options.map((opt) => (
        <div key={opt.option_id} className="card">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[15px] font-semibold leading-snug">{opt.title}</p>
            <span className={`tag shrink-0 ${opt.action === 'proposal'
              ? 'bg-accent-soft text-accent-deep' : 'bg-ink/5 text-muted'}`}>
              {opt.action === 'proposal' ? '可转修改提案' : '参考方向'}
            </span>
          </div>
          <p className="mt-1.5 text-[13px] leading-relaxed text-ink/80">{opt.detail}</p>
          <dl className="mt-2.5 grid gap-1.5 text-xs leading-relaxed">
            <div><dt className="inline font-medium text-emerald-700">收益：</dt>
                 <dd className="inline text-muted">{opt.tradeoffs.收益}</dd></div>
            <div><dt className="inline font-medium text-amber-700">代价：</dt>
                 <dd className="inline text-muted">{opt.tradeoffs.代价}</dd></div>
            <div><dt className="inline font-medium text-ink/70">适用条件：</dt>
                 <dd className="inline text-muted">{opt.tradeoffs.适用条件}</dd></div>
          </dl>
          {actionable && opt.action === 'proposal' && (
            <button className="btn-soft btn mt-3 w-full text-[13px]"
                    disabled={busy === opt.option_id || Boolean(staged)}
                    onClick={() => stage(opt.option_id)}>
              <ClipboardCheck size={15} />
              {busy === opt.option_id ? '生成提案中…' : '转为修改提案（需确认后生效）'}
            </button>
          )}
        </div>
      ))}

      {staged && (
        <div className="card border-accent/40">
          <p className="text-sm font-semibold">待确认提案 {staged.proposalId.slice(0, 12)}…</p>
          <ul className="mt-2 space-y-1 rounded-lg bg-canvas p-2.5 text-xs leading-relaxed">
            {staged.operations.map((op, i) => (
              <li key={i}>· {opSummary(op)}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            提案未生效。请输入明确表述来决定（例如「确认，按这个方案加重」或「不同意」）。
          </p>
          <textarea className="input mt-2 min-h-16" rows={2} value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="输入你的决定…" />
          <div className="mt-2 flex gap-2">
            <button className="btn-primary btn text-sm" disabled={!message.trim() || busy === 'confirm'}
                    onClick={decide}>
              {busy === 'confirm' ? '提交中…' : '提交决定'}
            </button>
            <button className="btn-ghost btn text-sm" onClick={() => setStaged(null)}>
              暂不决定
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-xs leading-relaxed text-red-600">{error}</p>}
      {result && <p className="text-xs leading-relaxed text-accent-deep">{result}</p>}

      <div className="flex gap-2">
        {actionable && (
          <button className="btn-ghost btn flex-1 text-[13px]" disabled={busy === 'dismiss'}
                  onClick={dismiss}>
            {busy === 'dismiss' ? '处理中…' : '忽略这条建议'}
          </button>
        )}
        {/* 失效/过期的洞察同样可以重新分析——数据漂移后这是主路径 */}
        <button className={`btn-ghost btn text-[13px] ${actionable ? 'flex-1' : 'w-full'}`}
                disabled={busy === 'regen'} onClick={regenerate}>
          {busy === 'regen' ? '分析中…' : '用最新数据重新分析'}
        </button>
      </div>
      <p className="text-2xs leading-relaxed text-faint">
        局限：{insight.limitations.slice(0, 3).join('；')}
        {insight.limitations.length > 3 ? '……' : ''}
      </p>
    </div>
  )
}
