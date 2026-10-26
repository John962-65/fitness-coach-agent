// P6-C：可以选择的方案（只读）+ 我的决定。
// 申请长期调整必须经由统一确认协议（propose → pending → 用户确认）。
import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox } from '../../components/Bits'
import type { CollaborationReport } from '../../types'

export function CollaborationOptions({ uid, report, insightId, onDecided }: {
  uid: string
  report: CollaborationReport
  insightId: string
  onDecided: () => void
}) {
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('')

  const decide = async (decision: 'ignore' | 'observe' | 'propose') => {
    setBusy(decision); setError(''); setNotice('')
    try {
      const out = await api.collaborationDecision(
        uid, insightId, decision, decision === 'propose' ? selected : undefined)
      setNotice(out.note)
      onDecided()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy('') }
  }

  return (
    <div className="space-y-2">
      {error && <ErrorBox message={error} />}
      {notice && (
        <p className="rounded-xl bg-accent-soft px-3 py-2 text-xs text-accent-deep">
          {notice}
        </p>
      )}
      <div role="radiogroup" aria-label="可以选择的方案" className="space-y-2">
        {report.candidate_options.map((o) => (
          <div key={o.option_id} role="radio" aria-checked={selected === o.option_id}
               tabIndex={0}
               onClick={() => setSelected(o.option_id)}
               onKeyDown={(e) => {
                 if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(o.option_id) }
               }}
               className={`cursor-pointer rounded-xl border p-3 transition-colors ${
                 selected === o.option_id
                   ? 'border-accent-deep/50 bg-accent-soft/60'
                   : 'border-line bg-surface hover:border-lineStrong'}`}>
            <p className="text-sm font-semibold">{o.title}</p>
            <p className="mt-0.5 text-2xs leading-relaxed text-muted">{o.detail}</p>
            {(o.limitations || []).map((lim, i) => (
              <p key={i} className="mt-1 text-2xs text-amber-700">{lim}</p>
            ))}
          </div>
        ))}
      </div>
      {report.decision_requirements.map((line, i) => (
        <p key={i} className="text-2xs leading-relaxed text-faint">· {line}</p>
      ))}
      <div className="flex flex-wrap gap-2 border-t border-line pt-3">
        <Button className="btn-sm" disabled={!selected || busy !== ''}
                onClick={() => decide('propose')}>
          <ShieldCheck size={14} /> 申请长期调整（走确认协议）
        </Button>
        <Button variant="ghost" className="btn-sm" disabled={busy !== ''}
                onClick={() => decide('observe')}>
          继续观察
        </Button>
        <Button variant="ghost" className="btn-sm" disabled={busy !== ''}
                onClick={() => decide('ignore')}>
          忽略
        </Button>
      </div>
    </div>
  )
}
