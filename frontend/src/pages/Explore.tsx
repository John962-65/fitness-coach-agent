import { useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import KnowledgePanel from '../components/KnowledgePanel'
import { ExerciseDetail, ExerciseSummary } from '../types'
import { useApp } from '../store'

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
  useEffect(() => {
    if (!detail) return
    fetch(`/api/users/${uid}/exercise-media?exercise_id=${detail.id}`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json())
      .then((r) => setMedia(r.links || []))
      .catch(() => setMedia([]))
  }, [detail, uid])

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
              {media.length > 0 && (
                <section>
                  <h4 className="label">我的教学媒体（视频导入关联）</h4>
                  <div className="space-y-2">
                    {media.map((m, i) => (
                      <div key={i} className="rounded-lg bg-neutral-800/60 p-2">
                        {m.clip_path ? (
                          <video controls preload="metadata" className="max-h-48 w-full rounded"
                                 src={`/api/media/${m.clip_path.match(/media\/([^/]+\/[^/]+)$/)?.[1] || ''
                                   }${localStorage.getItem('fc-access-token')
                                     ? `?access_token=${encodeURIComponent(localStorage.getItem('fc-access-token') || '')}` : ''}`} />
                        ) : m.cover_path ? (
                          <img alt="封面" className="max-h-40 rounded"
                               src={`/api/media/${m.cover_path.match(/media\/([^/]+\/[^/]+)$/)?.[1] || ''
                                 }${localStorage.getItem('fc-access-token')
                                   ? `?access_token=${encodeURIComponent(localStorage.getItem('fc-access-token') || '')}` : ''}`} />
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
