import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Card, Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { ApproachRevision, ApproachView, Profile, Trial } from '../types'

const STRUCTURE_LABEL: Record<string, string> = {
  full_body: '全身', upper_lower: '上下肢分化', ppl: '推拉腿分化',
  circuit: '循环训练', custom: '自定义',
}

export default function Mine() {
  const uid = useApp((s) => s.uid)
  const setUid = useApp((s) => s.setUid)
  const navigate = useNavigate()
  const [profile, setProfile] = useState<Profile | null>(null)
  const [summary, setSummary] = useState('')
  const [view, setView] = useState<ApproachView | null>(null)
  const [revisions, setRevisions] = useState<ApproachRevision[] | null>(null)
  const [trials, setTrials] = useState<Trial[] | null>(null)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [showRevisions, setShowRevisions] = useState(false)

  const load = useCallback(() => {
    api.profile(uid).then((r) => { setProfile(r.profile); setSummary(r.summary) })
      .catch((e) => setError(e.message))
    api.approach(uid).then(setView).catch(() => setView({ initialized: false }))
    api.revisions(uid).then((r) => setRevisions(r.revisions)).catch(() => setRevisions([]))
    api.trials(uid).then((r) => setTrials(r.trials)).catch(() => setTrials([]))
  }, [uid])
  useEffect(() => { load() }, [load])

  if (error) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!profile) return <Spinner />

  const exportData = () => {
    const blob = new Blob([JSON.stringify({ profile, approach: view, trials, exported_at: new Date().toISOString() }, null, 2)],
      { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `fitness-coach-${uid}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="我的" sub={`用户 ${uid}`} />

      <Card title="档案">
        <p className="whitespace-pre-wrap text-sm text-neutral-300">{summary}</p>
      </Card>

      <Card title="我的训练方式"
            right={view?.initialized
              ? <Tag tone="green">v{view.approach!.revision}</Tag>
              : undefined}>
        {!view?.initialized ? (
          <div>
            <Empty>还没建立「我的训练方式」——从现有计划一键初始化。</Empty>
            <button className="btn-ghost w-full"
                    onClick={() => api.initApproach(uid).then(() => load()).catch((e) => setNote(e.message))}>
              从当前计划初始化
            </button>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <p>结构：<b>{STRUCTURE_LABEL[view.approach!.structure.value]}</b>
              {view.approach!.structure.note && <span className="text-neutral-500"> · {view.approach!.structure.note}</span>}
            </p>
            <p>强度风格：{view.approach!.intensity_style.value}</p>
            {view.approach!.exercise_selection.length > 0 && (
              <div>
                <p className="label">动作选择（{view.approach!.exercise_selection.length} 项）</p>
                <div className="flex flex-wrap gap-1.5">
                  {view.approach!.exercise_selection.map((s) => (
                    <span key={s.exercise_id} className="tag bg-neutral-800 text-neutral-300">
                      {s.exercise_id}
                      {s.status !== 'active' && <b className="ml-1 text-accent">{s.status}</b>}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {(view.approach!.diet_approach.strategy || view.approach!.diet_approach.note) && (
              <p>饮食方式：{view.approach!.diet_approach.strategy || view.approach!.diet_approach.note}</p>
            )}
            {view.referenced?.active_trial && (
              <p className="text-xs text-sky-300">进行中的尝试：{view.referenced.active_trial.change_desc}</p>
            )}
            {view.referenced?.active_plan && view.referenced.active_plan.approach_revision != null
              && view.referenced.active_plan.approach_revision < view.approach!.revision && (
              <p className="text-xs text-amber-300">
                当前计划基于训练方式 v{view.referenced.active_plan.approach_revision}，落后于最新 v{view.approach!.revision}；
                去 AI 教练页商量是否重排。
              </p>
            )}
            <button className="btn-ghost w-full !py-2 text-xs"
                    onClick={() => setShowRevisions((s) => !s)}>
              {showRevisions ? '收起版本历史' : `版本历史（${revisions?.length ?? 0}）`}
            </button>
            {showRevisions && (
              <ul className="space-y-1.5">
                {(revisions || []).map((r) => (
                  <li key={r.revision} className="rounded-lg bg-neutral-800/60 p-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span><b>v{r.revision}</b> · {r.initiator === 'system_migration' ? '初始化' : r.initiator === 'ai' ? 'AI 建议' : '本人修改'}</span>
                      <span className="text-neutral-500">{r.created_at.slice(0, 10)}</span>
                    </div>
                    <p className="mt-0.5 text-neutral-400">{r.reason}</p>
                    {r.revision !== view.approach!.revision && (
                      <button className="mt-1 text-accent underline"
                              onClick={() => api.restoreRevision(uid, r.revision, `恢复到 v${r.revision}`)
                                .then(() => { setNote(`已恢复 v${r.revision} 为最新版本`); load() })
                                .catch((e: ApiError) => setNote(e.message))}>
                        恢复此版本
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Card>

      {note && <p className="text-center text-xs text-accent">{note}</p>}

      <Card title="个人尝试">
        {!trials?.length ? <Empty>暂无记录（可在 AI 教练页发起一次有边界的尝试）</Empty> : (
          <ul className="space-y-2 text-sm">
            {trials.map((t) => (
              <li key={t.id} className="rounded-lg bg-neutral-800/60 p-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{t.change_desc}</span>
                  {t.status === 'active'
                    ? <Tag tone={t.due_review ? 'amber' : 'blue'}>{t.due_review ? '该复盘了' : '进行中'}</Tag>
                    : <Tag tone="neutral">{({ keep: '保留', stop: '停止', adjust: '调整' } as Record<string, string>)[t.decision || ''] || t.decision}</Tag>}
                </div>
                <p className="mt-0.5 text-xs text-neutral-500">观察：{t.observe} · 停止条件：{t.stop_rule}</p>
                {t.outcome && <p className="mt-0.5 text-xs text-neutral-400">结果：{t.outcome}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="数据与设置">
        <div className="space-y-2">
          <button className="btn-ghost w-full !py-2 text-sm" onClick={exportData}>导出我的数据（JSON）</button>
          <div className="flex gap-2">
            <input className="input text-sm" placeholder="切换到其他用户 ID"
                   onKeyDown={(e) => {
                     if (e.key === 'Enter') {
                       const v = (e.target as HTMLInputElement).value.trim()
                       if (v) { setUid(v); navigate('/today') }
                     } }} />
            <button className="btn-ghost shrink-0 text-sm"
                    onClick={() => { setUid(''); navigate('/welcome') }}>新用户建档</button>
          </div>
        </div>
      </Card>

      <p className="px-2 pb-2 text-[11px] leading-relaxed text-neutral-600">
        本系统不提供医疗诊断或治疗建议；涉及伤病、疾病、孕期、用药的内容默认隔离并建议咨询专业人员。
        视频估计与模型推断不构成医学结论。
      </p>
    </div>
  )
}
