import { ArrowRight } from 'lucide-react'
import { CONFIDENCE, INSIGHT_STATUS, SPECIALIST_LABEL,
         relativeTime } from '../../lib/experts'
import { ExpertInsightSummary } from '../../types'

/** 专业分析摘要卡（今日页 / 专家中心 / 工作台列表共用） */
export default function InsightCard({ insight, onClick }:
  { insight: ExpertInsightSummary; onClick?: () => void }) {
  const status = INSIGHT_STATUS[insight.status] ?? { label: insight.status, tone: 'bg-ink/5 text-muted' }
  const conf = CONFIDENCE[insight.confidence]
  const clickable = Boolean(onClick)
  return (
    <button type="button" onClick={onClick} disabled={!clickable}
            className={`card w-full text-left transition-shadow
                        ${clickable ? 'hover:shadow-pop' : 'cursor-default'}`}>
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-accent-deep">
          {SPECIALIST_LABEL[insight.specialist] ?? insight.specialist}
        </span>
        <span className={`tag ${status.tone}`}>{status.label}</span>
        {conf && <span className={`tag ${conf.tone}`}>{conf.label}</span>}
        <span className="ml-auto shrink-0 text-2xs text-faint">
          {relativeTime(insight.generated_at)}
        </span>
      </div>
      <p className="mt-1.5 text-[15px] font-semibold leading-snug">{insight.title}</p>
      <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted">
        {insight.status_reason ?? insight.summary}
      </p>
      {clickable && (
        <p className="mt-2 flex items-center gap-1 text-xs font-medium text-accent-deep">
          查看分析依据与方案 <ArrowRight size={13} />
        </p>
      )}
    </button>
  )
}
