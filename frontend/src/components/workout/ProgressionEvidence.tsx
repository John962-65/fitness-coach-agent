// P5-C2：候选依据与限制展示。
// 所有数值都来自确定性上下文（fact_refs / comparability / data_quality），
// 本组件只做呈现，不推导新结论。
import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Tag } from '../Bits'
import type { ProgressionContext, ProgressionOption } from '../../types'

const FACT_METRIC_LABELS: Record<string, string> = {
  'working-sets': '正式组数',
  volume: '力量容量',
  sessions: '训练次数',
  'best-estimated-1rm': '最佳 e1RM（估算）',
  'max-reps': '最多次数',
  'min-assistance-kg': '最小辅助重量',
  'longest-set': '单组最长保持',
  'steady-cardio-seconds': '持续有氧时长',
  'steady-cardio-distance': '持续有氧距离',
  'interval-work-seconds': '间歇工作秒数',
  'interval-rounds': '间歇轮次',
}

export function factLabel(metric: string): string {
  return FACT_METRIC_LABELS[metric] || metric
}

/** 候选卡的"依据与限制"展开区。 */
export function OptionEvidence({ option, context }: {
  option: ProgressionOption
  context: ProgressionContext
}) {
  const facts = new Map((context.fact_refs || []).map((f) => [f.fact_id, f]))
  const basis = (option.basis_fact_ids || [])
    .map((fid) => facts.get(fid))
    .filter((f) => !!f)
  const dq = option.data_quality || {}
  return (
    <div className="space-y-2.5 text-2xs leading-relaxed text-muted">
      {basis.length > 0 && (
        <div>
          <p className="font-medium text-ink">依据（真实事实）</p>
          <ul className="mt-1 space-y-0.5">
            {basis.map((f) => (
              <li key={f.fact_id} className="nums">
                · {factLabel(f.metric)}：{String(f.value)}{f.unit || ''}
                <span className="ml-1 text-faint">（{f.status}）</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {(option.source_ids || []).length > 0 && (
        <p>来源：{option.source_ids.length} 条真实训练记录
          （{option.source_ids[0]} 等，可追溯）</p>
      )}
      {typeof dq.comparable_sessions === 'number' && (
        <p>可比记录：{dq.comparable_sessions} 次
          {typeof dq.increment_source === 'string' && (
            <> · 档位来源：{dq.increment_source === 'exercise_progression_metadata'
              ? '动作库已验证档位'
              : dq.increment_source === 'user_exercise_progression_metadata'
                ? '你配置的档位'
                : dq.increment_source === 'observed_history'
                  ? '历史重量差（未确认档位，仅供参考方向）'
                  : '未知档位'}</>
          )}
        </p>
      )}
      {(option.limitations || []).length > 0 && (
        <div>
          <p className="font-medium text-ink">限制</p>
          <ul className="mt-1 space-y-0.5">
            {option.limitations.map((line, i) => <li key={i}>· {line}</li>)}
          </ul>
        </div>
      )}
      {option.tradeoffs && (
        <div>
          {option.tradeoffs.benefits && <p>收益：{option.tradeoffs.benefits}</p>}
          {option.tradeoffs.costs && <p>代价：{option.tradeoffs.costs}</p>}
          {option.tradeoffs.conditions && <p>适用条件：{option.tradeoffs.conditions}</p>}
        </div>
      )}
    </div>
  )
}

/** 面板级的数据状态区：可比性、达成分类、恢复事实、安全限制。 */
export function PanelDataStatus({ context, blockedReasons }: {
  context: ProgressionContext
  blockedReasons: string[]
}) {
  const dq = context.data_quality || {}
  const comparability = context.comparability || {}
  const recovery = context.recovery_context || {}
  const safety = context.safety_context || {}
  const exclusions = Object.entries(dq.comparable_exclusions || {})
  const attainments = Object.entries(comparability.target_attainment || {})
  return (
    <div className="space-y-2 text-2xs leading-relaxed text-muted">
      <p>
        结构可比 {comparability.structurally_comparable?.length ?? 0}
        / 近期 {dq.recent_session_count ?? context.recent_sessions?.length ?? 0} 次
        {dq.latest_session_comparable === false && ' · 最近一次结构口径不同，未纳入同口径比较'}
        {dq.plan_context_stale && ' · 计划上下文已过期，未引用旧计划目标'}
        {dq.temporary_replacement && ' · 当前动作是本次临时替换'}
      </p>
      {attainments.length > 0 && (
        <p>目标达成：{attainments.map(([cid, att]) =>
          `#${cid} ${att.label || att.level}${att.note ? `（${att.note}）` : ''}`
        ).join('；')}</p>
      )}
      {exclusions.length > 0 && (
        <p>未纳入同口径比较：{exclusions.map(([cid, reasons]) =>
          `#${cid}（${reasons.join('、')}）`).join('；')}</p>
      )}
      {recovery.signals && recovery.signals.length > 0 && (
        <p>恢复自报（独立事实，不是诊断）：
          {recovery.signals.map((s) => `${s.metric}=${s.value}`).join('、')}
        </p>
      )}
      {safety.active_restrictions && safety.active_restrictions.length > 0 && (
        <p>生效训练限制：{(safety.summary_lines || []).join('；') || '见安全记录'}</p>
      )}
      {blockedReasons.map((line, i) => (
        <p key={i} className="font-medium text-amber-700">· {line}</p>
      ))}
    </div>
  )
}

/** 折叠容器：查看依据与限制。 */
export function EvidenceDisclosure({ summary, children }: {
  summary?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button className="btn-plain !px-0 text-xs"
              aria-expanded={open}
              onClick={() => setOpen(!open)}>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {summary || '查看依据与限制'}
      </button>
      {open && <div className="mt-2 animate-fade-up">{children}</div>}
    </div>
  )
}

export function AttainmentTag({ level, label }: { level: string; label?: string }) {
  const tone = level === 'at_top' ? 'green'
    : level === 'met_min' ? 'brand'
    : level === 'above_range' ? 'blue'
    : level === 'below_target' ? 'amber' : 'neutral'
  return <Tag tone={tone}>{label || level}</Tag>
}
