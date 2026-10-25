import { useState } from 'react'
import { ChevronDown, FileSearch } from 'lucide-react'
import { FINDING_KIND, sourceRefText } from '../../lib/experts'
import { ExpertInsight } from '../../types'

const STATUS_TONE: Record<string, string> = {
  observed: 'bg-emerald-50 text-emerald-700',
  estimated: 'bg-amber-50 text-amber-700',
  insufficient: 'bg-ink/5 text-faint',
}
const STATUS_LABEL: Record<string, string> = {
  observed: '记录', estimated: '估算', insufficient: '数据不足',
}

const FACT_METRIC: Record<string, string> = {
  sessions: '训练次数', 'sessions-per-week': '周频率', 'working-sets': '正式组数',
  volume: '总容量', 'heaviest-set': '最重组', 'best-estimated-1rm': '最佳估算 e1RM',
  'max-reps': '最多次数', 'max-added-weight': '最大附加负重',
  'min-assistance-kg': '最小辅助', 'longest-set': '单组最长', 'farthest-distance': '单组最远',
  'rpe-average': 'RPE 均值', training_days: '训练天数', avg_duration_min: '平均时长',
  'plan-scheduled-sessions': '计划应练', 'plan-completed-days': '计划完成',
  'plan-adherence': '计划完成率',
}

/** 证据面板：逐条发现 → 引用的事实与打卡追溯链（可展开） */
export default function EvidencePanel({ insight }: { insight: ExpertInsight }) {
  const [open, setOpen] = useState<string | null>(null)
  const byId = new Map(insight.facts_snapshot?.facts?.map((f) => [f.fact_id, f]) ?? [])
  return (
    <div className="space-y-2.5">
      {insight.findings.map((f) => {
        const facts = f.fact_ids.map((id) => byId.get(id)).filter(Boolean)
        const isOpen = open === f.finding_id
        return (
          <div key={f.finding_id} className="rounded-xl border border-line bg-surface/60">
            <button type="button"
                    className="flex w-full items-start gap-2.5 p-3 text-left"
                    onClick={() => setOpen(isOpen ? null : f.finding_id)}>
              <span className="tag mt-0.5 shrink-0 bg-ink/5 text-muted">
                {FINDING_KIND[f.kind] ?? f.kind}
              </span>
              <span className="min-w-0 flex-1 text-[13px] leading-relaxed">{f.text}</span>
              <ChevronDown size={16} className={`mt-0.5 shrink-0 text-muted transition-transform
                                                  ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && (
              <div className="border-t border-line px-3 pb-3 pt-2.5">
                {f.evidence === 'unverified' && (
                  <p className="mb-2 text-xs text-amber-700">该说明没有数据引用支撑（上下文性说明）</p>
                )}
                {facts.length > 0 && (
                  <ul className="space-y-1.5">
                    {facts.map((fact) => (
                      <li key={fact!.fact_id} className="flex flex-wrap items-center gap-1.5 text-xs">
                        <span className={`tag ${STATUS_TONE[fact!.status] ?? ''}`}>
                          {STATUS_LABEL[fact!.status] ?? fact!.status}
                        </span>
                        <span className="font-medium">
                          {FACT_METRIC[fact!.metric] ?? fact!.metric}
                          {fact!.exercise_id ? `（${fact!.exercise_id}）` : ''}：
                        </span>
                        <span className="nums">
                          {fact!.value === null ? '不足' : `${fact!.value}${fact!.unit}`}
                        </span>
                        <span className="text-faint">· {fact!.calculation}</span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs leading-relaxed text-muted">
                  <FileSearch size={12} className="mr-1 inline" />
                  数据来源：{f.source_ids.map(sourceRefText).join('、') || '—'}
                </p>
              </div>
            )}
          </div>
        )
      })}
      {insight.knowledge_refs.length > 0 && (
        <div className="rounded-xl border border-line bg-surface/60 p-3">
          <p className="text-xs font-semibold text-muted">知识参考（共享检索命中）</p>
          <ul className="mt-1.5 space-y-1">
            {insight.knowledge_refs.map((k, i) => (
              <li key={i} className="text-xs leading-relaxed text-ink/75">
                [{k.engine}] {k.title}
                <span className="ml-1 text-faint">（来源：{k.provenance}）</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
