import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BookOpen, MessageCircleHeart, UsersRound } from 'lucide-react'
import { api, ApiError } from '../api'
import { ErrorBox, PageHeader, Segmented, Spinner } from '../components/Bits'
import ExpertCard from '../components/experts/ExpertCard'
import ExpertTaskStatus from '../components/experts/ExpertTaskStatus'
import InsightCard from '../components/experts/InsightCard'
import { useApp } from '../store'
import { ExpertInsightSummary, ExpertOverview, ExpertTask } from '../types'

export default function Experts() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [overview, setOverview] = useState<ExpertOverview | null>(null)
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [tasks, setTasks] = useState<ExpertTask[]>([])
  const [tab, setTab] = useState<'insights' | 'tasks'>('insights')
  const [error, setError] = useState('')
  const [savingSettings, setSavingSettings] = useState(false)

  function load() {
    Promise.all([
      api.expertsOverview(uid),
      api.expertInsights(uid, { limit: 10 }),
      api.expertTasks(uid),
    ]).then(([o, i, t]) => {
      setOverview(o); setInsights(i.insights); setTasks(t.tasks)
    }).catch((e) => setError((e as ApiError).message))
  }

  useEffect(load, [uid])
  if (error) return <div className="pt-4"><ErrorBox message={error} onRetry={load} /></div>
  if (!overview) return <Spinner />

  async function toggleProactive(on: boolean) {
    if (!overview) return
    setSavingSettings(true)
    try {
      const settings = await api.saveExpertSettings(uid, {
        proactive_enabled: on,
        min_interval_minutes: overview.settings.min_interval_minutes,
      })
      setOverview({ ...overview, settings })
    } catch { /* 保持原状态；下一次加载会纠正 */ }
    finally { setSavingSettings(false) }
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="专家" sub="一个主教练 + 五位专业顾问 + 共享知识研究" />

      {/* 主教练 + 共享知识研究 */}
      <div className="grid gap-3 sm:grid-cols-2">
        <Link to="/experts/chat" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
            <MessageCircleHeart size={21} className="text-accent" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">主教练</p>
            <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted">
              整合各顾问的事实与分歧，呈现方案取舍；修改需你确认
            </p>
          </div>
        </Link>
        <Link to="/experts/knowledge" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft">
            <BookOpen size={21} className="text-accent-deep" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold">运动科学知识</p>
            <p className="mt-0.5 line-clamp-2 text-xs leading-relaxed text-muted">
              带来源与审核状态的知识检索；未经审核的内容不作为处方依据
            </p>
          </div>
        </Link>
      </div>

      {/* 五位专业顾问 */}
      <h3 className="mb-2 mt-5 flex items-center gap-2 text-sm font-semibold">
        <UsersRound size={16} /> 专业工作台
      </h3>
      <div className="grid gap-3 sm:grid-cols-2">
        {overview.specialists.map((spec) => (
          <ExpertCard key={spec.specialist} spec={spec} />
        ))}
      </div>

      {/* 主动分析设置 */}
      <div className="card mt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold">主动分析</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              训练完成后自动生成训练科学回顾（确定性计算，不调用聊天模型）。
              关闭后仍可随时在工作台手动分析。
            </p>
          </div>
          <button type="button" role="switch" aria-checked={overview.settings.proactive_enabled}
                  disabled={savingSettings}
                  onClick={() => toggleProactive(!overview.settings.proactive_enabled)}
                  className={`relative h-7 w-12 shrink-0 rounded-full transition-colors ${
                    overview.settings.proactive_enabled ? 'bg-accent' : 'bg-ink/15'}`}>
            <span className={`absolute top-0.5 size-6 rounded-full bg-white shadow transition-all ${
              overview.settings.proactive_enabled ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
        </div>
        {overview.pending_tasks.length > 0 && (
          <p className="mt-2 text-xs text-amber-700">
            有 {overview.pending_tasks.length} 个分析任务排队中
          </p>
        )}
      </div>

      {/* 分析结果 / 任务 */}
      <div className="mb-2 mt-5 flex items-center justify-between">
        <h3 className="text-sm font-semibold">分析结果与任务</h3>
        <Segmented value={tab} onChange={setTab}
                   options={[{ value: 'insights', label: `分析（${insights.length}）` },
                             { value: 'tasks', label: `任务（${tasks.length}）` }]} />
      </div>
      {tab === 'insights' ? (
        insights.length === 0 ? (
          <div className="card text-sm leading-relaxed text-muted">
            还没有专业分析。完成一次训练并保存后，训练科学顾问会自动生成
            可追溯的训练后回顾；也可以去
            <Link to="/experts/training" className="mx-1 font-medium text-accent-deep underline underline-offset-2">
              训练科学工作台
            </Link>
            手动分析。
          </div>
        ) : (
          <div className="space-y-3">
            {insights.map((ins) => (
              <InsightCard key={ins.id} insight={ins}
                           onClick={() => navigate(`/experts/training?insight=${ins.id}`)} />
            ))}
          </div>
        )
      ) : (
        <div className="space-y-2">
          {tasks.length === 0
            ? <p className="card text-sm text-muted">暂无任务记录。</p>
            : tasks.map((t) => <ExpertTaskStatus key={t.id} task={t} />)}
        </div>
      )}

      <p className="mt-5 px-1 text-2xs leading-relaxed text-faint">
        本平台为 AI 辅助软件，不暗示由持证专业人员实时提供服务；
        涉及伤病、疾病等医疗问题请咨询合格专业人员。
      </p>
    </div>
  )
}
