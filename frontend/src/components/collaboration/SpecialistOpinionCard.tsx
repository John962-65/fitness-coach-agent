// P6-C：单个专家意见卡。
import { Tag } from '../../components/Bits'
import { SPECIALIST_LABELS, DIRECTION_LABELS } from './CollaborationOverview'
import type { SpecialistOpinion } from '../../types'
export function SpecialistOpinionCard({ opinion }: { opinion: SpecialistOpinion }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">
          {SPECIALIST_LABELS[opinion.specialist] || opinion.specialist}
        </p>
        <div className="flex flex-wrap gap-1">
          {opinion.directions.map((d) => (
            <Tag key={d.direction}
                 tone={d.direction === 'safety_gate' ? 'red'
                   : d.direction === 'insufficient_data' ? 'neutral'
                   : 'brand'}>
              {DIRECTION_LABELS[d.direction] || d.direction}
            </Tag>
          ))}
        </div>
      </div>
      <ul className="mt-1.5 space-y-0.5 text-2xs leading-relaxed text-muted">
        {opinion.observations.map((line, i) => <li key={i}>· {line}</li>)}
      </ul>
      {opinion.interpretations.map((line, i) => (
        <p key={i} className="mt-1 text-2xs leading-relaxed text-muted">{line}</p>
      ))}
      {opinion.recommendations.map((line, i) => (
        <p key={i} className="mt-1 text-2xs leading-relaxed text-ink">{line}</p>
      ))}
      {opinion.limitations.map((line, i) => (
        <p key={i} className="mt-1 text-2xs leading-relaxed text-faint">限制：{line}</p>
      ))}
    </div>
  )
}

