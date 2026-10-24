// 动作详情独立页：教学 / 技术分析 / 知识依据 三个标签页（M3.2 + M4 能力全保留）
import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { PlayCircle, Upload, TriangleAlert } from 'lucide-react'
import { api } from '../api'
import {
  Chip, Empty, ErrorBox, Segmented, Spinner, SubHeader, Tag,
} from '../components/Bits'
import { CoverPlaceholder, useSignedMedia } from '../components/media'
import { ExerciseDetail } from '../types'
import { useApp } from '../store'
import { PATTERN_LABEL } from './Explore'

interface MotionFault { code: string; label?: string; value?: number; hint?: string }
interface MotionAnalysisItem {
  id: number; exercise_id: string; view: string; status: string; error: string | null
  video_path?: string
  created_at: string
  result: {
    supported: boolean; frames: number; note?: string; view?: string
    faults: MotionFault[]
    reps: { rep: number; start_s: number; end_s: number; peak_s: number }[]
    summary: Record<string, number>
  }
}

const MUSCLE_LABEL: Record<string, string> = {
  chest: '胸', back: '背', shoulders: '肩', biceps: '二头', triceps: '三头',
  quads: '股四头', hamstrings: '腘绳', glutes: '臀', calves: '小腿', core: '核心',
}

export default function ExploreDetail() {
  const { exerciseId } = useParams()
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ExerciseDetail | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'teach' | 'analysis' | 'basis'>('teach')

  // M3.2：用户教学媒体（封面/演示片段）
  const [media, setMedia] = useState<{ cover_path: string | null; clip_path: string | null; sentence: string }[]>([])
  // M4：动作视频分析（上传/任务/时间轴/对比）
  const [analyses, setAnalyses] = useState<MotionAnalysisItem[]>([])
  const [maNote, setMaNote] = useState('')
  const [compare, setCompare] = useState<{ a: number; b: number } | null>(null)
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null)
  const [analysisVideo, setAnalysisVideo] = useState<string | null>(null)

  const authHeaders = (): Record<string, string> => {
    const t = localStorage.getItem('fc-access-token')
    return t ? { 'X-Access-Token': t } : {}
  }

  const loadAnalyses = useCallback(() => {
    if (!exerciseId) return
    fetch(`/api/users/${uid}/motion-analyses?exercise_id=${exerciseId}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((r) => setAnalyses((r.analyses || []) as MotionAnalysisItem[]))
      .catch(() => setAnalyses([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exerciseId, uid])

  useEffect(() => {
    if (!exerciseId) return
    api.exerciseDetail(exerciseId).then(setDetail).catch((e) => setError(e.message))
    fetch(`/api/users/${uid}/exercise-media?exercise_id=${exerciseId}`, { headers: authHeaders() })
      .then((r) => r.json())
      .then((r) => setMedia(r.links || []))
      .catch(() => setMedia([]))
    loadAnalyses()
    setCompare(null); setCompareResult(null); setAnalysisVideo(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exerciseId, uid, loadAnalyses])

  const uploadAnalysis = async (file: File) => {
    if (!exerciseId) return
    setMaNote('已上传，分析中…')
    const form = new FormData()
    form.append('exercise_id', exerciseId)
    form.append('view', 'side')
    form.append('video', file)
    const res = await fetch(`/api/users/${uid}/motion-analyses`, {
      method: 'POST', headers: authHeaders(), body: form,
    })
    const body = await res.json()
    if (!res.ok) { setMaNote(body.detail?.error || '上传失败'); return }
    const id = body.analysis_id as number
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      const list = await fetch(`/api/users/${uid}/motion-analyses?exercise_id=${exerciseId}`,
        { headers: authHeaders() }).then((r) => r.json())
      const me = (list.analyses || []).find((x: { id: number }) => x.id === id)
      if (me && me.status !== 'processing') { setMaNote(''); loadAnalyses(); return }
    }
    setMaNote('分析仍在进行（本地推理较慢），稍后刷新查看')
  }

  if (error) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <SubHeader title="动作详情" onBack={() => navigate('/explore')} />
        <ErrorBox message={error} />
      </div>
    )
  }
  if (!detail) return <Spinner />

  const muscles = (detail.primary as string[] | undefined) || []

  return (
    <div className="mx-auto w-full max-w-3xl">
      <SubHeader title={detail.name} sub={PATTERN_LABEL[(detail.pattern as string) || ''] || (detail.pattern as string) || ''}
                 onBack={() => navigate('/explore')} />

      {/* 头图 + 概要 */}
      <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
        {media.length > 0 && media[0].clip_path ? (
          <ClipPlayer uid={uid} path={media[0].clip_path} />
        ) : media.length > 0 && media[0].cover_path ? (
          <DetailCover uid={uid} path={media[0].cover_path} name={detail.name} />
        ) : (
          <CoverPlaceholder name={detail.name} className="flex h-40 w-full items-center justify-center" iconSize={40} />
        )}
        <div className="p-4">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-xl font-bold">{detail.name}</h2>
            {detail.status === 'approved'
              ? <Tag tone="green">已审核</Tag>
              : <Tag tone="amber">未审核</Tag>}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(detail.aliases as string[] | undefined)?.length ? (
              <Tag>{(detail.aliases as string[]).join('、')}</Tag>
            ) : null}
            {muscles.map((m) => <Tag key={m} tone="brand">{MUSCLE_LABEL[m] || m}</Tag>)}
            {((detail.equipment as string[] | undefined) || []).map((e) => <Tag key={e}>{e}</Tag>)}
          </div>
          {detail.status !== 'approved' && (
            <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-xs leading-relaxed text-amber-800">
              <TriangleAlert size={15} className="mt-0.5 shrink-0" />
              该动作的结构化属性（关节压力/替代关系）尚未经审核。
            </div>
          )}
        </div>
      </div>

      <Segmented className="my-4"
        options={[
          { value: 'teach', label: '教学' },
          { value: 'analysis', label: '动作分析' },
          { value: 'basis', label: '知识依据' },
        ]}
        value={tab} onChange={setTab} />

      {/* ---- 教学 ---- */}
      {tab === 'teach' && (
        <div className="space-y-4">
          {media.length > 0 && (
            <div className="card">
              <h3 className="mb-2.5 text-[15px] font-semibold">我的教学媒体（视频导入关联）</h3>
              <div className="space-y-3">
                {media.map((m, i) => (
                  <div key={i} className="overflow-hidden rounded-xl border border-line">
                    {m.clip_path && <ClipPlayer uid={uid} path={m.clip_path} />}
                    {!m.clip_path && m.cover_path && <DetailCover uid={uid} path={m.cover_path} name={detail.name} />}
                    <p className="px-3 py-2 text-xs leading-relaxed text-muted">依据：{m.sentence}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          {typeof detail.setup === 'string' && detail.setup && (
            <div className="card">
              <h3 className="mb-1.5 text-[15px] font-semibold">准备</h3>
              <p className="text-sm leading-relaxed text-ink/90">{detail.setup}</p>
            </div>
          )}
          {Array.isArray(detail.cues) && detail.cues.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-[15px] font-semibold">执行要点</h3>
              <ul className="space-y-1.5">
                {detail.cues.map((c, i) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed text-ink/90">
                    <span className="nums mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full
                                     bg-accent-soft text-2xs font-bold text-accent-deep">{i + 1}</span>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(detail.errors) && detail.errors.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-[15px] font-semibold">常见错误</h3>
              <ul className="space-y-1.5">
                {detail.errors.map((c, i) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed text-muted">
                    <TriangleAlert size={15} className="mt-0.5 shrink-0 text-amber-500" />{c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(detail.self_check) && detail.self_check.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-[15px] font-semibold">自查</h3>
              <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed text-muted">
                {detail.self_check.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
            </div>
          )}
          {media.length === 0 && !detail.setup && !(detail.cues?.length) && (
            <Empty title="教学指导尚未完善">
              {detail.status === 'approved'
                ? '该动作的结构化资料（关节压力/替代关系）已通过审核；图文教学要点尚未录入。可先用「动作分析」上传训练视频，或查看「知识依据」。'
                : '该动作的图文教学要点尚未录入，且结构化属性还未审核。'}
            </Empty>
          )}
        </div>
      )}

      {/* ---- 动作分析（首批：深蹲类/硬拉/RDL/卧推，侧面） ---- */}
      {tab === 'analysis' && (
        <div className="space-y-4">
          <div className="card">
            <h3 className="text-[15px] font-semibold">上传训练视频分析</h3>
            <p className="mb-3 mt-1 text-xs leading-relaxed text-muted">
              首批支持：深蹲类 / 硬拉 / RDL / 卧推（侧面视角）。估计结果基于画面几何量，不构成医学结论。
            </p>
            {analysisVideo && (
              <video id="ma-video" controls src={analysisVideo}
                     className="mb-3 max-h-64 w-full rounded-xl bg-black" />
            )}
            <label className="btn-ghost w-full cursor-pointer">
              <Upload size={15} /> 选择视频（mp4 / webm / mov / mkv）
              <input type="file" accept="video/mp4,video/webm,video/quicktime,.mkv" className="hidden"
                     onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadAnalysis(f) }} />
            </label>
            {maNote && <p className="mt-2 text-center text-xs text-accent-deep">{maNote}</p>}
          </div>

          {analyses.length === 0 ? (
            <Empty icon={<PlayCircle size={20} />} title="还没有分析记录">
              上传一段该动作的训练视频，查看重复次数与动作提示。
            </Empty>
          ) : analyses.map((m) => (
            <div key={m.id} className="card">
              <div className="flex items-center justify-between gap-2">
                <p className="nums text-[13px] text-muted">
                  #{m.id} · {m.created_at.slice(0, 16)} · {m.view} 视角
                </p>
                <Tag tone={m.status === 'ready' ? 'green' : m.status === 'failed' ? 'red' : 'amber'}>
                  {{ ready: '已分析', failed: '失败', processing: '分析中' }[m.status] || m.status}
                </Tag>
              </div>
              {m.error && <p className="mt-1.5 text-sm text-red-600">{m.error}</p>}
              {m.status === 'ready' && (
                <div className="mt-2.5 space-y-2.5">
                  {!m.result.supported ? (
                    <p className="rounded-xl bg-amber-50 p-3 text-[13px] leading-relaxed text-amber-800">
                      {m.result.note}
                    </p>
                  ) : (
                    <>
                      <p className="nums text-[13px] text-muted">
                        {m.result.frames} 帧 · 估计 {m.result.reps.length} 次重复
                        {m.result.faults.length > 0
                          ? ` · ${m.result.faults.length} 项提示` : ' · 未命中已覆盖的可见项目'}
                      </p>
                      {m.result.reps.length > 0 && (
                        <div className="flex flex-wrap gap-1.5">
                          {m.result.reps.map((r) => (
                            <Chip key={r.rep} active={false}
                                  onClick={() => {
                                    const v = document.getElementById('ma-video') as HTMLVideoElement | null
                                    if (v) { v.currentTime = r.start_s; v.play() }
                                  }}>
                              第{r.rep}次 @{r.start_s}s
                            </Chip>
                          ))}
                        </div>
                      )}
                      {m.result.faults.length > 0 && (
                        <ul className="space-y-1.5 rounded-xl bg-amber-50 p-3">
                          {m.result.faults.map((f, i) => (
                            <li key={i} className="text-[13px] leading-relaxed text-amber-800">
                              ⚠️ {f.label || f.code}
                              {f.value !== undefined && ` 值=${f.value}`}
                              {f.hint && <span className="text-amber-700/70">（{f.hint}）</span>}
                            </li>
                          ))}
                        </ul>
                      )}
                      {m.result.note && <p className="text-xs leading-relaxed text-faint">{m.result.note}</p>}
                    </>
                  )}
                  <div className="flex flex-wrap items-center gap-3 border-t border-line pt-2.5 text-[13px]">
                    <button className="font-medium text-accent-deep hover:underline"
                            onClick={async () => {
                              const file = m.video_path?.match(/media\/[^/]+\/([^/]+)$/)?.[1] || ''
                              if (!file) return
                              try {
                                const sgn = await api.mediaSign(uid, file)
                                setAnalysisVideo(`/api/media/${uid}/${file}?sig=${sgn.sig}&exp=${sgn.exp}`)
                              } catch {
                                setAnalysisVideo(`/api/media/${uid}/${file}`) // 本机无令牌模式
                              }
                            }}>
                      查看视频
                    </button>
                    <button className="font-medium text-sky-600 hover:underline"
                            onClick={() => setCompare((c) => c && c.a !== m.id ? { ...c, b: m.id } : { a: m.id, b: 0 })}>
                      {compare?.a === m.id ? '对比 A ✓' : '设为对比 A'}
                    </button>
                    {compare?.a && compare.a !== m.id && (
                      <button className="font-medium text-sky-600 hover:underline"
                              onClick={async () => {
                                const r = await api.motionCompare(uid, compare.a, m.id) as Record<string, unknown>
                                setCompareResult(r)
                              }}>与 A 对比</button>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}

          {compareResult && (
            <div className="card border-sky-200 bg-sky-50/50">
              <h3 className="text-[15px] font-semibold text-sky-800">两次对比（几何量变化，非评分）</h3>
              <pre className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-sky-900">
                {JSON.stringify(compareResult.compare, null, 1)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* ---- 知识依据 ---- */}
      {tab === 'basis' && (
        <div className="space-y-4">
          {detail.joint_stress && Object.keys(detail.joint_stress).length > 0 && (
            <div className="card">
              <h3 className="mb-2.5 text-[15px] font-semibold">关节压力</h3>
              <p className="mb-1 text-2xs text-faint">数值来自结构化属性表</p>
              <div className="space-y-2">
                {Object.entries(detail.joint_stress).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-3">
                    <span className="w-16 shrink-0 text-sm text-ink">{k}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-ink/8">
                      <div className="h-full rounded-full bg-accent"
                           style={{ width: `${Math.min(100, (Number(v) || 0) * 10)}%` }} />
                    </div>
                    <span className="nums w-8 shrink-0 text-right text-xs text-muted">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {Array.isArray(detail.notes) && detail.notes.length > 0 && (
            <div className="card">
              <h3 className="mb-2 text-[15px] font-semibold">知识依据</h3>
              <ul className="space-y-1.5">
                {detail.notes.map((n, i) => (
                  <li key={i} className="text-[13px] leading-relaxed text-muted">· {n}</li>
                ))}
              </ul>
            </div>
          )}
          {!detail.joint_stress && !(detail.notes?.length) && (
            <Empty title="暂无知识依据">该动作尚未关联结构化属性或知识条目。</Empty>
          )}
        </div>
      )}
    </div>
  )
}

/** 详情页封面（签名加载，加载失败回退占位） */
function DetailCover({ uid, path, name }: { uid: string; path: string; name: string }) {
  const src = useSignedMedia(uid, path)
  if (!src) return <div className="h-40 w-full animate-pulse-soft bg-ink/6" />
  return <img alt={`${name} 封面`} src={src} className="max-h-72 w-full object-cover" />
}

/** 演示片段（签名加载） */
function ClipPlayer({ uid, path }: { uid: string; path: string }) {
  const src = useSignedMedia(uid, path)
  if (!src) return <div className="aspect-video w-full animate-pulse-soft bg-ink/6" />
  return <video controls preload="metadata" src={src} className="aspect-video w-full bg-black" />
}
