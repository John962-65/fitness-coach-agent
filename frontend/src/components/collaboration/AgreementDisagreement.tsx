// P6-C：共识 / 分歧 / 未知 / 安全门。
import type { CollaborationReport } from '../../types'
import { SPECIALIST_LABELS, DIRECTION_LABELS } from './CollaborationOverview'
export function AgreementDisagreement({ report }: { report: CollaborationReport }) {
  return (
    <div className="space-y-2">
      {report.safety_gates.map((g, i) => (
        <div key={i} className="rounded-xl border border-red-200 bg-red-50 p-3">
          <p className="text-xs font-semibold text-red-700">
            安全门（优先级最高，不因其他意见改变）
          </p>
          <p className="mt-1 text-2xs leading-relaxed text-red-700">{g.note}</p>
        </div>
      ))}
      {report.disagreements.map((d, i) => (
        <div key={i} className="rounded-xl border border-amber-300 bg-amber-50 p-3">
          <p className="text-xs font-semibold text-amber-800">
            专家分歧（{d.between.map((s) => SPECIALIST_LABELS[s] || s).join(' × ')}）
          </p>
          <ul className="mt-1.5 space-y-1 text-2xs leading-relaxed text-amber-900">
            {d.positions.map((p) => (
              <li key={p.specialist}>
                · {SPECIALIST_LABELS[p.specialist] || p.specialist}
                认为「{DIRECTION_LABELS[p.direction] || p.direction}」：{p.note}
              </li>
            ))}
          </ul>
          {d.shared_facts.length > 0 && (
            <p className="mt-1 text-2xs text-amber-800">
              双方共同依据 {d.shared_facts.length} 条事实
            </p>
          )}
          <p className="mt-1 text-2xs text-amber-800">
            还缺少：{d.missing_information.join('；')}
          </p>
          <p className="mt-0.5 text-2xs text-amber-800">{d.maintain_option}</p>
        </div>
      ))}
      {report.agreements.length > 0 && (
        <div className="rounded-xl border border-line bg-surface p-3">
          <p className="text-xs font-semibold text-ink">共识</p>
          <ul className="mt-1 space-y-0.5 text-2xs text-muted">
            {report.agreements.map((a, i) => (
              <li key={i}>
                · {a.between.map((s) => SPECIALIST_LABELS[s] || s).join('、')}
                一致认为「{DIRECTION_LABELS[a.direction] || a.direction}」
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.unknowns.length > 0 && (
        <div className="rounded-xl border border-line bg-canvas p-3">
          <p className="text-xs font-semibold text-ink">数据不足（未知不当作零值）</p>
          <ul className="mt-1 space-y-0.5 text-2xs text-muted">
            {report.unknowns.map((u, i) => (
              <li key={i}>
                · {SPECIALIST_LABELS[u.specialist] || u.specialist}：{u.note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
