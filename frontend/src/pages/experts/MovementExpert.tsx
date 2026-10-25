import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Dumbbell, MessageCircleHeart, Sparkles } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Empty, ErrorBox, PageHeader, Segmented, Spinner } from '../../components/Bits'
import { ModelFallback } from '../../components/exercise3d/ModelFallback'
import MotionAnalysisReport from '../../components/movement/MotionAnalysisReport'
import MotionUpload from '../../components/movement/MotionUpload'
import VideoComparison from '../../components/movement/VideoComparison'
import { DEMO_FIVE, STATUS_ZH, viewCompatible, type TechProfile } from '../../lib/movement'
import { useApp } from '../../store'
import type {
  ExerciseDetail, ExpertInsight, ExpertInsightSummary, TrainingRestriction,
} from '../../types'

const Exercise3DViewer = lazy(() => import('../../components/exercise3d/Exercise3DViewer'))

type Tab = 'learn' | 'analysis' | 'history' | 'insights'

const TABS: { value: Tab; label: string }[] = [
  { value: 'learn', label: '三维教学' },
  { value: 'analysis', label: '视频分析' },
  { value: 'history', label: '历史技术记录' },
  { value: 'insights', label: '顾问洞察' },
]

interface AnalysisItem {
  id: number
  exercise_id: string
  view: string
  status: string
  error: string | null
  result: Record<string, unknown> | null
  video_path: string
  created_at: string
  tech_profile: TechProfile | null
}

/** 动作技术顾问工作台（P4）：学习 → 分析 → 对照 → 档案 → 洞察 */
export default function MovementExpert() {
  const uid = useApp((s) => s.uid)
  const [exerciseId, setExerciseId] = useState<string>(DEMO_FIVE[0].id)
  const [detail, setDetail] = useState<ExerciseDetail | null>(null)
  const [tab, setTab] = useState<Tab>('learn')
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [, setCompare] = useState<{ a: number; b: number } | null>(null)
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null)
  const [restrictions, setRestrictions] = useState<TrainingRestriction[]>([])
  const [insights, setInsights] = useState<ExpertInsightSummary[]>([])
  const [insightDetail, setInsightDetail] = useState<ExpertInsight | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    Promise.all([
      api.exerciseDetail(exerciseId),
      api.motionAnalyses(uid, exerciseId),
      api.restrictions(uid).catch(() => ({ restrictions: [] })),
      api.expertInsights(uid, { specialist: 'movement', limit: 10 }),
    ]).then(([d, m, r, i]) => {
      setDetail(d)
      setAnalyses((m.analyses ?? []) as AnalysisItem[])
      setRestrictions(r.restrictions ?? [])
      setInsights(i.insights)
      setSelected(((m.analyses ?? [])[0] as AnalysisItem | undefined)?.id ?? null)
    }).catch((e) => setError((e as ApiError).message))
  }, [uid, exerciseId])
  useEffect(load, [load])

  const selectedAnalysis = analyses.find((a) => a.id === selected) ?? null
  const demo = detail?.demos?.model_3d ?? null
  const custom = !DEMO_FIVE.some((d) => d.id === exerciseId)
  const teaching = detail?.teaching_content
  const comparePair = useMemo(() => {
    const ok = analyses.filter((a) => a.status === 'ready')
    return ok.length >= 2 ? { a: ok[1].id, b: ok[0].id } : null
  }, [analyses])

  async function runCompare(a: number, b: number) {
    setCompare({ a, b }); setCompareResult(null)
    try {
      const r = await api.motionCompare(uid, a, b) as Record<string, unknown>
      setCompareResult(r)
    } catch (e) {
      setError((e as ApiError).message)
    }
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader title="动作技术工作台" sub="学习 · 观察 · 对照 · 复盘（首批五个三维动作）"
        right={<span className="tag bg-accent-soft text-accent-deep">
          <Dumbbell size={13} /> 顾问
        </span>} />

      {/* 动作选择（稳定 exercise_id；自定义动作无公共三维/分析支持时如实标注） */}
      <div className="mb-3 flex flex-wrap gap-1.5">
        {DEMO_FIVE.map((d) => (
          <button key={d.id}
                  className={`tag ${exerciseId === d.id ? 'bg-night text-white'
                              : 'bg-ink/5 text-muted'}`}
                  onClick={() => { setExerciseId(d.id); setSelected(null); setCompare(null) }}>
            {d.name}
          </button>
        ))}
      </div>
      {error && <div className="mb-3"><ErrorBox message={error} onRetry={load} /></div>}
      <div className="mb-4"><Segmented value={tab} onChange={setTab} options={TABS} /></div>

      {/* ---- 三维教学 ---- */}
      {tab === 'learn' && (!detail ? <Spinner /> : (
        <div className="space-y-4">
          {demo ? (
            <div className="card !p-3">
              <Suspense fallback={<ModelFallback mode="loading" />}>
                <Exercise3DViewer key={detail.id} demo={demo}
                                  onFallback={() => { }} />
              </Suspense>
              <p className="mt-2 px-1 text-2xs leading-relaxed text-faint">
                三维演示用于观察动作模式与阶段节奏；演示不等于对你的动作正确性判定，
                也不因动画演示了某动作就意味着当前适合你执行（见训练限制）。
              </p>
            </div>
          ) : (
            <Empty icon={<Dumbbell size={22} />} title="该动作暂无公共三维演示">
              公共三维演示目前覆盖首批五个动作；{detail.name} 的图文教学仍然可用。
            </Empty>
          )}
          {/* 结构化教学（审核状态如实标注） */}
          {teaching && (
            <div className="card">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold">结构化教学</p>
                <span className="tag bg-ink/5 text-muted">
                  {STATUS_ZH[teaching.review_status] ?? teaching.review_status}
                </span>
                {teaching.review_status === 'draft' && (
                  <span className="text-2xs text-amber-700">
                    草稿状态：不作为已确认的专业指导依据
                  </span>
                )}
              </div>
              {Object.entries(teaching.sections).map(([key, sec]) => (
                <div key={key} className="mt-2 border-t border-line pt-2">
                  <p className="text-xs font-semibold">
                    {key} · <span className="text-faint">{STATUS_ZH[sec.status] ?? sec.status}</span>
                  </p>
                  <ul className="mt-1 space-y-1">
                    {(sec.items as (string | Record<string, string>)[] | undefined)
                      ?.slice(0, 6).map((it, i) => (
                      <li key={i} className="text-[13px] leading-relaxed">
                        {typeof it === 'string' ? `· ${it}` : (
                          <span>
                            · {it.error}
                            {it.consequence && <span className="text-muted">（{it.consequence}）</span>}
                            {it.fix && <span className="block pl-4 text-muted">→ {it.fix}</span>}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
          <div className="rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
            返回训练时原有会话与逐组草稿不受影响；本页所有教学资源按稳定
            exercise_id 关联，自定义动作不会被自动挂到内置三维模型上。
          </div>
        </div>
      ))}

      {/* ---- 视频分析 + 对照 ---- */}
      {tab === 'analysis' && (
        <div className="space-y-4">
          {custom ? (
            <Empty icon={<Dumbbell size={22} />} title="该动作暂不在视频分析支持范围">
              视频分析当前覆盖首批五个三维动作（深蹲/卧推/硬拉/划船/肩推）。
            </Empty>
          ) : (
            <>
              <div className="card">
                <p className="mb-2 text-sm font-semibold">上传我的动作视频</p>
                <MotionUpload exerciseId={exerciseId}
                              exerciseName={DEMO_FIVE.find(
                                (d) => d.id === exerciseId)?.name ?? exerciseId}
                              onDone={(aid) => { setSelected(aid); load() }} />
              </div>
              {analyses.length === 0 ? (
                <p className="card text-sm text-muted">
                  还没有分析记录。上传后自动完成：质量检查 → 运动特征观察 →
                  动作阶段切分（全程本地推理，视频不离开本机）。
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    {analyses.map((a) => (
                      <button key={a.id}
                              className={`tag ${selected === a.id ? 'bg-night text-white'
                                          : 'bg-ink/5 text-muted'}`}
                              onClick={() => setSelected(a.id)}>
                        #{a.id} · {a.created_at.slice(5, 10)} · {STATUS_ZH[a.status] ?? a.status}
                      </button>
                    ))}
                  </div>
                  {selectedAnalysis && (
                    <>
                      {selectedAnalysis.status === 'failed' ? (
                        <ErrorBox message={`分析失败：${selectedAnalysis.error ?? '未知原因'}（视频与记录仍在，可重传）`} />
                      ) : (
                        <MotionAnalysisReport
                          profile={selectedAnalysis.tech_profile}
                          result={selectedAnalysis.result}
                          note={selectedAnalysis.result?.note as string | null ?? null}
                          restrictionHint={restrictions.find((r) =>
                            (r.affected_activities.regions ?? []).some(
                              (rg) => ['knee', 'lower_back', 'shoulder', 'wrist', 'hip', 'ankle', 'elbow']
                                .includes(rg)))?.restriction_description ?? null} />
                      )}
                      {/* 分屏对照（usable + 有三维时） */}
                      {demo && selectedAnalysis.tech_profile
                        && selectedAnalysis.tech_profile.video_quality.status === 'usable' && (
                        <div className="card">
                          <p className="mb-2 text-sm font-semibold">视频 × 三维对照</p>
                          <VideoComparison
                            videoPath={selectedAnalysis.video_path}
                            demo={demo}
                            phases={selectedAnalysis.tech_profile.phase_timestamps} />
                        </div>
                      )}
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}

      {/* ---- 历史技术记录 ---- */}
      {tab === 'history' && (
        <div className="space-y-4">
          {analyses.length < 2 ? (
            <Empty icon={<Sparkles size={22} />} title="历史记录不足两次">
              同一动作在不同日期上传两次以上，即可在这里做确定性对比
              （需可比视角与观测质量；跨模型版本数值不解释为动作变化）。
            </Empty>
          ) : (
            <>
              {comparePair && (
                <div className="card">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold">两次分析对比</p>
                    <button className="btn-soft btn text-xs"
                            onClick={() => runCompare(comparePair.a, comparePair.b)}>
                      对比 #{comparePair.a} ↔ #{comparePair.b}
                    </button>
                  </div>
                  {compareResult && (
                    <CompareView data={compareResult}
                                 profiles={analyses.map((a) => a.tech_profile)} />
                  )}
                </div>
              )}
              <ul className="card divide-y divide-line">
                {analyses.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2 py-2.5 text-[13px]">
                    <span>
                      #{a.id} · {a.created_at.slice(0, 10)} · {a.view} 视角 ·{' '}
                      {a.tech_profile?.video_quality.status ?? '旧版分析'}
                      {a.tech_profile?.user_notes ? ` · ${a.tech_profile.user_notes}` : ''}
                    </span>
                    <button className="btn-ghost btn text-xs text-red-600"
                            onClick={async () => {
                              await api.deleteMotionAnalysis(uid, a.id); load()
                            }}>
                      删除
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* ---- 顾问洞察 ---- */}
      {tab === 'insights' && (
        <div className="space-y-3">
          {insights.length === 0 ? (
            <Empty icon={<Sparkles size={22} />} title="还没有动作技术洞察">
              上传视频并完成分析后，动作技术顾问会基于技术档案生成可追溯的回顾
              （观察/教学参考/无法判断的部分/安全限制）。
            </Empty>
          ) : (
            <>
              <div className="space-y-3">
                {insights.map((ins) => (
                  <button key={ins.id}
                          className="card w-full text-left"
                          onClick={async () => {
                            const d = await api.expertInsight(uid, ins.id)
                            setInsightDetail(d)
                            if (d.status === 'ready') {
                              api.markInsightViewed(uid, ins.id).then(load).catch(() => {})
                            }
                          }}>
                    <p className="text-[15px] font-semibold">{ins.title}</p>
                    <p className="mt-1 line-clamp-2 text-xs text-muted">{ins.summary}</p>
                    <p className="mt-1 text-2xs text-faint">
                      {ins.status} · {ins.confidence} · {ins.generated_at.slice(5, 16).replace('T', ' ')}
                    </p>
                  </button>
                ))}
              </div>
              {insightDetail && (
                <div className="card">
                  <p className="text-sm font-semibold">{insightDetail.title}</p>
                  <p className="mt-1 text-[13px] leading-relaxed">{insightDetail.summary}</p>
                  <ul className="mt-2 space-y-1.5">
                    {insightDetail.findings.map((f, i) => (
                      <li key={i} className="rounded-lg bg-canvas p-2.5 text-xs leading-relaxed">
                        {f.text}
                      </li>
                    ))}
                  </ul>
                  <h4 className="mb-1.5 mt-3 text-xs font-semibold">局限</h4>
                  <ul className="space-y-0.5 text-2xs leading-relaxed text-faint">
                    {insightDetail.limitations.map((l, i) => <li key={i}>· {l}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}
          <Link to="/experts/chat" className="card flex items-center gap-3.5 transition-shadow hover:shadow-pop">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-night">
              <MessageCircleHeart size={21} className="text-accent" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold">咨询动作技术顾问</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                聊天是工作台的辅助；分析结论以这里的确定性观察为准
              </p>
            </div>
          </Link>
        </div>
      )}
    </div>
  )
}

function CompareView({ data, profiles }: {
  data: Record<string, unknown>; profiles: (TechProfile | null)[] }) {
  const comparable = viewCompatible(profiles?.[0] ?? null, profiles?.[1] ?? null)
  return (
    <div className="mt-2 space-y-2 text-xs leading-relaxed">
      {!comparable && (
        <p className="rounded-lg bg-amber-50 p-2 text-amber-700">
          两次分析的视角或质量不可比——对比结果仅供参考，不构成进步/退步判断
          （模型升级造成的数值变化同样不解释为动作变化）。
        </p>
      )}
      {Object.entries(data).map(([k, v]) => (
        <p key={k}><span className="font-medium">{k}</span>：{JSON.stringify(v)}</p>
      ))}
    </div>
  )
}
