import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import KnowledgePanel from '../components/KnowledgePanel'
import { ExerciseDetail, ExerciseSummary } from '../types'
import { useApp } from '../store'

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

const MUSCLES = ['chest', 'back', 'shoulders', 'biceps', 'triceps',
  'quads', 'hamstrings', 'glutes', 'calves', 'core']

export default function Explore() {
  const uid = useApp((s) => s.uid)
  const [pane, setPane] = useState<'exercises' | 'knowledge'>('exercises')
  const [q, setQ] = useState('')
  const [muscle, setMuscle] = useState('')
  const [items, setItems] = useState<ExerciseSummary[] | null>(null)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<ExerciseDetail | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      api.exercises({ q, muscle })
        .then((r) => setItems(r.exercises))
        .catch((e) => setError(e.message))
    }, 200)
    return () => clearTimeout(t)
  }, [q, muscle])

  // M3.2：详情打开时拉取该动作的用户教学媒体（封面/演示片段）
  const [media, setMedia] = useState<{ cover_path: string | null; clip_path: string | null; sentence: string }[]>([])
  // M4：动作视频分析（上传/任务/时间轴/对比）
  const [analyses, setAnalyses] = useState<MotionAnalysisItem[]>([])
  const [maNote, setMaNote] = useState('')
  const [compare, setCompare] = useState<{ a: number; b: number } | null>(null)
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null)
  const [analysisVideo, setAnalysisVideo] = useState<string | null>(null)
  const loadAnalyses = useCallback(() => {
    if (!detail) return
    fetch(`/api/users/${uid}/motion-analyses?exercise_id=${detail.id}`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json())
      .then((r) => setAnalyses((r.analyses || []) as MotionAnalysisItem[]))
      .catch(() => setAnalyses([]))
  }, [detail, uid])
  useEffect(() => {
    if (!detail) return
    fetch(`/api/users/${uid}/exercise-media?exercise_id=${detail.id}`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json())
      .then((r) => setMedia(r.links || []))
      .catch(() => setMedia([]))
    loadAnalyses()
    setCompare(null); setCompareResult(null); setAnalysisVideo(null)
  }, [detail, uid, loadAnalyses])

  const uploadAnalysis = async (file: File) => {
    if (!detail) return
    setMaNote('已上传，分析中…')
    const form = new FormData()
    form.append('exercise_id', detail.id)
    form.append('view', 'side')
    form.append('video', file)
    const res = await fetch(`/api/users/${uid}/motion-analyses`, {
      method: 'POST',
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
      body: form,
    })
    const body = await res.json()
    if (!res.ok) { setMaNote(body.detail?.error || '上传失败'); return }
    const id = body.analysis_id as number
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 1500))
      const list = await fetch(
        `/api/users/${uid}/motion-analyses?exercise_id=${detail.id}`, {
        headers: localStorage.getItem('fc-access-token')
          ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
      }).then((r) => r.json())
      const me = (list.analyses || []).find((x: { id: number }) => x.id === id)
      if (me && me.status !== 'processing') { setMaNote(''); loadAnalyses(); return }
    }
    setMaNote('分析仍在进行（本地推理较慢），稍后刷新查看')
  }

  return (
    <div className="space-y-3 pt-4">
      <PageHeader title="探索" sub="动作库与统一知识库（文件/博主观点/教练卡/我的导入）" />
      <div className="flex gap-2">
        <button onClick={() => setPane('exercises')}
                className={`btn flex-1 ${pane === 'exercises' ? 'bg-accent text-neutral-950' : 'bg-neutral-800'}`}>
          动作库
        </button>
        <button onClick={() => setPane('knowledge')}
                className={`btn flex-1 ${pane === 'knowledge' ? 'bg-accent text-neutral-950' : 'bg-neutral-800'}`}>
          知识库
        </button>
      </div>
      {pane === 'knowledge' ? <KnowledgePanel uid={uid} /> : null}
      {pane !== 'exercises' ? null : (
      <>
      <p className="text-xs text-neutral-500">{items?.length ?? '…'} 个动作 · 含教学要点与关节压力标注</p>
      <input className="input" placeholder="搜索名称或别名" value={q}
             onChange={(e) => setQ(e.target.value)} />
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        <button onClick={() => setMuscle('')}
                className={`tag shrink-0 ${!muscle ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-300'}`}>全部</button>
        {MUSCLES.map((m) => (
          <button key={m} onClick={() => setMuscle(m)}
                  className={`tag shrink-0 ${muscle === m ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-300'}`}>{m}</button>
        ))}
      </div>
      {error && <ErrorBox message={error} />}
      {!items && !error && <Spinner />}
      {items?.length === 0 && <Empty>没有匹配的动作</Empty>}
      <ul className="space-y-2">
        {items?.map((ex) => (
          <li key={ex.id}>
            <button className="card w-full text-left"
                    onClick={() => api.exerciseDetail(ex.id).then(setDetail).catch(() => { /* 详情失败不阻塞 */ })}>
              <div className="flex items-center justify-between">
                <span className="font-medium">{ex.name}</span>
                {ex.status === 'approved'
                  ? <Tag tone="green">已审核</Tag>
                  : <Tag tone="amber">未审核</Tag>}
              </div>
              <p className="mt-0.5 text-xs text-neutral-500">
                {ex.pattern} · {ex.primary.join('、') || '—'} · {ex.equipment.join('/') || '自重'}
              </p>
            </button>
          </li>
        ))}
      </ul>

      {detail && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/70" onClick={() => setDetail(null)}>
          <div className="max-h-[85vh] w-full overflow-y-auto rounded-t-2xl bg-neutral-900 p-4"
               onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-lg font-semibold">{detail.name}</h3>
              <button className="text-neutral-400" onClick={() => setDetail(null)}>关闭</button>
            </div>
            {detail.status !== 'approved' && (
              <p className="mb-2 rounded-lg bg-amber-950/40 p-2 text-xs text-amber-300">
                该动作的结构化属性（关节压力/替代关系）尚未经审核。
              </p>
            )}
            <div className="space-y-3 text-sm">
              <section>
                <h4 className="label">动作视频分析（首批：深蹲类/硬拉/RDL/卧推，侧面）</h4>
              {analysisVideo && (
                <video id="ma-video" controls src={analysisVideo} className="mb-2 max-h-56 w-full rounded" />
              )}
                <input type="file" accept="video/mp4,video/webm,video/quicktime,.mkv"
                       onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadAnalysis(f) }} />
                {maNote && <p className="mt-1 text-xs text-accent">{maNote}</p>}
                <div className="mt-2 space-y-2">
                  {analyses.map((m) => (
                    <div key={m.id} className="rounded-lg bg-neutral-800/60 p-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span>#{m.id} · {m.created_at.slice(0, 16)} · {m.view} 视角</span>
                        <Tag tone={m.status === 'ready' ? 'green' : m.status === 'failed' ? 'red' : 'amber'}>
                          {{ ready: '已分析', failed: '失败', processing: '分析中' }[m.status] || m.status}
                        </Tag>
                      </div>
                      {m.error && <p className="text-red-400">{m.error}</p>}
                      {m.status === 'ready' && (
                        <div className="mt-1 space-y-1">
                          {!m.result.supported
                            ? <p className="text-amber-300">{m.result.note}</p>
                            : <>
                                <p className="text-neutral-400">
                                  {m.result.frames} 帧 · {m.result.reps.length} 次重复（画面内估计）
                                  {m.result.faults.length > 0
                                    ? ` · ${m.result.faults.length} 项提示` : ' · 未命中已覆盖的可见项目'}
                                </p>
                                <div className="flex flex-wrap gap-1">
                                  {m.result.reps.map((r) => (
                                    <button key={r.rep} className="tag bg-neutral-700 text-neutral-200"
                                            onClick={() => {
                                              const v = document.getElementById('ma-video') as HTMLVideoElement | null
                                              if (v) { v.currentTime = r.start_s; v.play() }
                                            }}>
                                      第{r.rep}次 @{r.start_s}s
                                    </button>
                                  ))}
                                </div>
                                <ul className="space-y-0.5">
                                  {m.result.faults.map((f, i) => (
                                    <li key={i} className="text-amber-300">
                                      ⚠️ {f.label || f.code}
                                      {f.value !== undefined && ` 值=${f.value}`}
                                      {f.hint && <span className="text-neutral-500">（{f.hint}）</span>}
                                    </li>
                                  ))}
                                </ul>
                                <p className="text-neutral-600">{m.result.note}</p>
                              </>}
                          <div className="flex gap-2">
                            <button className="text-accent underline"
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
                            <button className="text-sky-400 underline"
                                    onClick={() => setCompare((c) => c && c.a !== m.id ? { ...c, b: m.id } : { a: m.id, b: 0 })}>
                              {compare?.a === m.id ? '对比 A ✓' : '设为对比 A'}
                            </button>
                            {compare?.a && compare.a !== m.id && (
                              <button className="text-sky-400 underline"
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
                </div>
                {compareResult && (
                  <div className="mt-2 rounded-lg bg-sky-950/30 p-2 text-xs">
                    <p className="font-semibold text-sky-300">两次对比（几何量变化，非评分）</p>
                    <pre className="mt-1 whitespace-pre-wrap text-neutral-300">
                      {JSON.stringify(compareResult.compare, null, 1)}
                    </pre>
                  </div>
                )}
              </section>
              {media.length > 0 && (
                <section>
                  <h4 className="label">我的教学媒体（视频导入关联）</h4>
                  <div className="space-y-2">
                    {media.map((m, i) => (
                      <div key={i} className="rounded-lg bg-neutral-800/60 p-2">
                        {m.clip_path ? (
                          <SignedMedia uid={uid} path={m.clip_path} kind="video" />
                        ) : m.cover_path ? (
                          <SignedMedia uid={uid} path={m.cover_path} kind="img" />
                        ) : null}
                        <p className="mt-1 text-xs text-neutral-500">依据：{m.sentence}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}
              {typeof detail.setup === 'string' && detail.setup && (
                <section><h4 className="label">准备</h4><p className="text-neutral-300">{detail.setup}</p></section>
              )}
              {Array.isArray(detail.cues) && detail.cues.length > 0 && (
                <section><h4 className="label">执行要点</h4>
                  <ul className="list-disc space-y-0.5 pl-4 text-neutral-300">
                    {detail.cues.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </section>
              )}
              {Array.isArray(detail.errors) && detail.errors.length > 0 && (
                <section><h4 className="label">常见错误</h4>
                  <ul className="list-disc space-y-0.5 pl-4 text-neutral-400">
                    {detail.errors.map((c, i) => <li key={i}>{c}</li>)}
                  </ul>
                </section>
              )}
              {detail.joint_stress && (
                <section><h4 className="label">关节压力（数值来自结构化属性表）</h4>
                  <p className="text-neutral-400">
                    {Object.entries(detail.joint_stress).map(([k, v]) => `${k}:${v}`).join(' · ')}
                  </p>
                </section>
              )}
              {Array.isArray(detail.notes) && detail.notes.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-xs text-neutral-500">
                  {detail.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
      </>
      )}
    </div>
  )
}


// M5.1 P1-5：签名媒体（10 分钟短时 sig 替代长期令牌入 URL）
function SignedMedia({ uid, path, kind }: { uid: string; path: string; kind: 'video' | 'img' }) {
  const [src, setSrc] = useState('')
  useEffect(() => {
    const file = path.match(/media\/[^/]+\/([^/]+)$/)?.[1] || ''
    if (!file) return
    api.mediaSign(uid, file)
      .then((s) => setSrc(`/api/media/${uid}/${file}?sig=${s.sig}&exp=${s.exp}`))
      .catch(() => setSrc(`/api/media/${uid}/${file}`))  // 本机无令牌模式
  }, [uid, path])
  if (!src) return null
  return kind === 'video'
    ? <video controls preload="metadata" className="max-h-48 w-full rounded" src={src} />
    : <img alt="封面" className="max-h-40 rounded" src={src} />
}
