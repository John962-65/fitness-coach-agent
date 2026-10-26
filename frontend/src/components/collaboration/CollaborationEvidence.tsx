// P6-C：事实来源及局限（共享事实包展示）。
import type { CollaborationReport } from '../../types'
import { DOMAIN_LABELS } from './CollaborationOverview'

export function CollaborationEvidence({ report }: { report: CollaborationReport }) {
  return (
    <div className="space-y-1 text-2xs leading-relaxed text-muted">
      {report.shared_facts.map((f) => (
        <p key={f.fact_id} className="nums">
          · [{DOMAIN_LABELS[f.domain] || f.domain}] {f.metric}
          ={typeof f.value === 'object' ? JSON.stringify(f.value) : String(f.value)}
          {f.unit ? ` ${f.unit}` : ''}
          <span className="ml-1 text-faint">{f.calculation}</span>
          {f.limitations.map((lim, i) => (
            <span key={i} className="ml-1 text-faint">（{lim}）</span>
          ))}
        </p>
      ))}
      <p className="text-faint">
        每条事实带来源与版本（source_revisions）；数据修订后旧报告自动失效。
      </p>
    </div>
  )
}
