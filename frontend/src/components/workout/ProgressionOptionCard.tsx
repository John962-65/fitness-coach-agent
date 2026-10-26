// P5-C2：单个候选方案卡。
// 不兼容的候选只展示方向（没有"仅本次采用"入口），绝不硬套字段。
import { Tag } from '../Bits'
import { AttainmentTag, EvidenceDisclosure, OptionEvidence } from './ProgressionEvidence'
import type { ProgressionContext, ProgressionOption } from '../../types'

const CATEGORY_META: Record<string, { label: string; tone: 'brand' | 'green' | 'amber' | 'blue' | 'neutral' }> = {
  maintain: { label: '维持', tone: 'neutral' },
  'complete-target-reps': { label: '完成目标', tone: 'brand' },
  'increase-load': { label: '加重', tone: 'amber' },
  'adjust-volume': { label: '调整训练量', tone: 'blue' },
  'observe-recovery': { label: '恢复观察', tone: 'amber' },
}

export function formatTarget(key: string, value: number | string): string {
  if (key === 'weight_kg') return `${value} kg`
  if (key === 'assistance_kg') return `辅助 ${value} kg`
  if (key === 'reps') return `${value} 次`
  if (key === 'sets') return `${value} 组`
  return `${key}=${value}`
}

export default function ProgressionOptionCard({ option, index, selected,
                                                context, applyBlockedReason,
                                                onSelect }: {
  option: ProgressionOption
  index: number
  selected: boolean
  context: ProgressionContext
  applyBlockedReason?: string | null
  onSelect: () => void
}) {
  const meta = CATEGORY_META[option.category]
    || { label: option.category, tone: 'neutral' as const }
  const targets = Object.entries(option.proposed_targets || {})
  return (
    <div role="radio" aria-checked={selected} tabIndex={0}
         onClick={onSelect}
         onKeyDown={(e) => {
           if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() }
         }}
         className={`cursor-pointer rounded-xl border p-3 transition-colors ${
           selected ? 'border-accent-deep/50 bg-accent-soft/60'
                    : 'border-line bg-surface hover:border-lineStrong'}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold leading-snug">
            {['①', '②', '③', '④', '⑤', '⑥'][index] || '·'} {option.title}
          </p>
          {targets.length > 0 && (
            <p className="nums mt-1 text-xs text-muted">
              候选目标：{targets.map(([k, v]) => formatTarget(k, v)).join(' · ')}
              <span className="ml-1 text-faint">（候选值，非已完成记录）</span>
            </p>
          )}
          {option.data_quality?.latest_attainment_label != null && (
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
              最近达成：
              <AttainmentTag
                level={String(option.data_quality.latest_target_attainment ?? '')}
                label={String(option.data_quality.latest_attainment_label)} />
            </p>
          )}
          {applyBlockedReason && (
            <p className="mt-1.5 text-2xs leading-relaxed text-amber-700">
              仅可查看方向：{applyBlockedReason}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Tag tone={meta.tone}>{meta.label}</Tag>
          {(option.action_scope || []).includes('plan') && option.plan_proposal && (
            <Tag tone="brand">可长期化</Tag>
          )}
        </div>
      </div>
      <div className="mt-2" onClick={(e) => e.stopPropagation()}>
        <EvidenceDisclosure>
          <OptionEvidence option={option} context={context} />
        </EvidenceDisclosure>
      </div>
    </div>
  )
}
