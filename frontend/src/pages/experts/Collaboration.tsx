// P6-C：跨专家协作工作台。
// 不要求用户打开多个聊天窗口：选择场景 → 请求联合分析（确定性）→
// 共享事实 / 各方观点 / 共识与分歧 / 只读方案 → 用户决定。
import { useCallback, useEffect, useState } from 'react'
import { PageHeader, ErrorBox, Spinner, Tag, Button, Notice } from '../../components/Bits'
import { api, ApiError } from '../../api'
import { useApp } from '../../store'
import type { ExpertInsight } from '../../types'
import { AgreementDisagreement } from '../../components/collaboration/AgreementDisagreement'
import { CollaborationOverview } from '../../components/collaboration/CollaborationOverview'
import { CollaborationOptions } from '../../components/collaboration/CollaborationOptions'
import { CollaborationEvidence } from '../../components/collaboration/CollaborationEvidence'
import { SpecialistOpinionCard } from '../../components/collaboration/SpecialistOpinionCard'

const SCENARIOS = [
  { key: 'training-recovery', label: '训练 × 恢复',
    desc: '下一次训练如何安排：表现事实与自报恢复并列' },
  { key: 'training-nutrition', label: '训练 × 营养',
    desc: '表现变化与已记录营养：先看记录能否支撑分析' },
  { key: 'movement-rehab', label: '动作技术 × 康复辅助',
    desc: '视频观察与身体不适/限制并列，不互相归因' },
]

export default function Collaboration() {
  const uid = useApp((s) => s.uid)
  const [scenario, setScenario] = useState(SCENARIOS[0].key)
  const [insight, setInsight] = useState<ExpertInsight | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const request = useCallback(() => {
    setLoading(true); setError(''); setNotice('')
    api.requestCollaboration(uid, scenario)
      .then((out) => {
        if (out.insight) {
          setInsight(out.insight)
          api.markInsightViewed(uid, out.insight.id).catch(() => {})
        } else {
          setNotice(`分析未完成：${out.error || '未知原因'}`)
        }
      })
      .catch((e: ApiError) => setError(e.message))
      .finally(() => setLoading(false))
  }, [uid, scenario])

  // 已有该场景的有效报告则直接展示（读取时懒失效在服务端判定）
  useEffect(() => {
    api.expertInsights(uid, { specialist: 'collaboration', limit: 10 })
      .then((r) => {
        const fresh = r.insights.find((i) =>
          i.insight_type === 'collaboration-review'
          && i.input_refs?.scenario === scenario
          && (i.status === 'ready' || i.status === 'viewed'))
        if (fresh) {
          return api.expertInsight(uid, fresh.id).then(setInsight)
        }
        setInsight(null)
      })
      .catch(() => setInsight(null))
  }, [uid, scenario])

  const report = insight?.facts_snapshot?.collaboration

  return (
    <div className="mx-auto min-h-dvh w-full max-w-xl px-4 pb-10 pt-6">
      <PageHeader title="跨专家协作" sub="共享事实 · 各自观点 · 分歧保留 · 你来决定" />
      <div className="mt-4 space-y-3">
        <div className="grid grid-cols-3 gap-2">
          {SCENARIOS.map((s) => (
            <button key={s.key}
                    onClick={() => { setScenario(s.key); setInsight(null) }}
                    aria-pressed={scenario === s.key}
                    className={`rounded-xl border p-2.5 text-left transition-colors ${
                      scenario === s.key
                        ? 'border-accent-deep/50 bg-accent-soft/60'
                        : 'border-line bg-surface'}`}>
              <p className="text-xs font-semibold">{s.label}</p>
              <p className="mt-0.5 text-2xs leading-relaxed text-muted">{s.desc}</p>
            </button>
          ))}
        </div>
        <Button block variant="ghost" disabled={loading} onClick={request}>
          {loading ? '分析中…' : '请求联合分析（确定性，不调聊天）'}
        </Button>
        {error && <ErrorBox message={error} />}
        {notice && <Notice>{notice}</Notice>}
        {loading && <Spinner label="正在构建跨领域事实包并收集各方观点…" />}

        {insight && (
          <div className="rounded-xl border border-line bg-canvas p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">{insight.title}</p>
              <Tag tone={insight.status === 'ready' || insight.status === 'viewed'
                ? 'green' : 'neutral'}>
                {insight.status === 'invalidated' ? '已失效'
                  : insight.status === 'dismissed' ? '已忽略' : '有效'}
              </Tag>
            </div>
            {insight.status_reason && (
              <p className="mt-1 text-2xs text-amber-700">{insight.status_reason}</p>
            )}
            <p className="mt-1 text-xs leading-relaxed text-muted">{insight.summary}</p>
          </div>
        )}

        {insight && report && (
          <div className="space-y-3">
            <section className="rounded-xl border border-line p-3">
              <p className="text-xs font-semibold text-ink">联合分析主题与参与顾问</p>
              <div className="mt-1.5"><CollaborationOverview report={report} /></div>
            </section>
            <section className="space-y-2">
              <p className="text-xs font-semibold text-ink">不同专业观点</p>
              {report.specialist_opinions.map((o) => (
                <SpecialistOpinionCard key={o.specialist} opinion={o} />
              ))}
            </section>
            <section>
              <p className="mb-2 text-xs font-semibold text-ink">
                共识、分歧与未知
              </p>
              <AgreementDisagreement report={report} />
            </section>
            <section>
              <p className="mb-2 text-xs font-semibold text-ink">可以选择的方案</p>
              <CollaborationOptions uid={uid} report={report}
                                    insightId={insight.id}
                                    onDecided={() => setNotice('已记录你的决定')} />
            </section>
            <section>
              <p className="mb-2 text-xs font-semibold text-ink">事实来源及局限</p>
              <CollaborationEvidence report={report} />
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
