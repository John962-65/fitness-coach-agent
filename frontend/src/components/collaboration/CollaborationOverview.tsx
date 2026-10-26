// P6-C：联合工作台组件——共享事实 / 专家意见 / 共识与分歧 / 方案与证据。
// 全部数值来自确定性事实包；分歧被并列保留，不投票合并。
import type { CollaborationReport } from '../../types'

export const SPECIALIST_LABELS: Record<string, string> = {
  training_science: '训练科学',
  nutrition: '营养',
  recovery: '恢复',
  rehabilitation: '康复辅助',
  movement: '动作技术',
  collaboration: '主教练',
}

export const DOMAIN_LABELS: Record<string, string> = {
  training: '训练', nutrition: '营养', body: '身体',
  recovery: '恢复', rehabilitation: '康复', movement: '动作',
}

export const DIRECTION_LABELS: Record<string, string> = {
  maintain_or_progress: '可按进阶引擎推进',
  investigate_decline: '表现下行需要排查',
  observe_and_reduce_risk: '观察并控制当次压力',
  no_signal: '恢复信号未见持续偏高',
  records_incomplete: '记录不完整，先补记录',
  records_observable: '记录相对完整',
  safety_gate: '安全门生效',
  no_restriction: '当前无生效限制',
  insufficient_data: '数据不足',
  observational_only: '仅保守观察',
}

export function CollaborationOverview({ report }: { report: CollaborationReport }) {
  return (
    <div className="space-y-1.5 text-xs leading-relaxed text-muted">
      <p className="text-ink">{report.question}</p>
      <p>参与顾问：{report.participants
        .map((p) => SPECIALIST_LABELS[p] || p).join('、')}</p>
      <p>共享事实 {report.shared_facts.length} 条
        （{[...new Set(report.shared_facts.map((f) => f.domain))]
          .map((d) => DOMAIN_LABELS[d] || d).join('、')}）</p>
      <p className="text-2xs text-faint">
        规则 {report.rules_version}；分歧并列保留，不投票合并；所有方案只读。
      </p>
    </div>
  )
}
