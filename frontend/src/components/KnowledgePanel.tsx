// M3 知识库面板：统一检索（md/博主观点/教练卡/我的导入）+ 导入 + 待审核
import { useCallback, useEffect, useState } from 'react'
import { BookOpenText, ShieldAlert, Upload } from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Card, Empty, ErrorBox, Field, Input, Segmented, Spinner, Tag, Textarea,
} from './Bits'

interface SearchHit {
  engine: string
  ref: string
  title: string
  snippet: string
  provenance: string
  status: string
}

interface SearchResult {
  keywords: string[]
  engines: Record<string, { hits: SearchHit[]; draft_matches?: number; note?: string }>
}

interface ImportedClaim {
  id: number
  content: string
  claim_type: string
  status: string
  risk_flag: string | null
  duplicate_of: { ref: string; similarity: number } | null
  conflict_with: { ref: string; similarity: number } | null
  source_title: string
}

const ENGINE_LABEL: Record<string, string> = {
  knowledge_md: '知识文件',
  blogger_claims: '博主观点',
  coach_cards: '教练卡',
  user_imports: '我的导入',
}

const TYPE_LABEL: Record<string, string> = {
  method: '方法', principle: '原理', cue: '发力', nutrition: '营养', other: '其他',
}

const PATTERNS = ['squat','hinge','lunge','h_push','v_push','h_pull','v_pull','isolation','core','carry']

export default function KnowledgePanel({ uid }: { uid: string }) {
  const [tab, setTab] = useState<'search' | 'import'>('search')
  const [q, setQ] = useState('')
  const [result, setResult] = useState<SearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const [claims, setClaims] = useState<ImportedClaim[] | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [importResult, setImportResult] = useState<string>('')
  const [error, setError] = useState<{ message: string; details?: string[] } | null>(null)

  const [proposals, setProposals] = useState<{ id: number; name: string; sentence: string | null }[]>([])
  const [propNote, setPropNote] = useState('')
  const loadClaims = useCallback(() => {
    api.knowledgeClaims(uid)
      .then((r) => setClaims((r.claims as unknown as ImportedClaim[])))
      .catch(() => setClaims([]))
    fetch(`/api/users/${uid}/exercise-proposals`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json()).then((r) => setProposals(r.proposals || [])).catch(() => setProposals([]))
  }, [uid])
  useEffect(() => { loadClaims() }, [loadClaims])

  const doSearch = () => {
    if (!q.trim()) return
    setSearching(true); setError(null)
    api.knowledgeSearch(uid, q)
      .then((r) => setResult(r as SearchResult))
      .catch((e: ApiError) => setError({ message: e.message }))
      .finally(() => setSearching(false))
  }

  const doImport = () => {
    setError(null); setImportResult('')
    api.knowledgeImport(uid, { title: title || '未命名资料', kind: 'text', content })
      .then((r) => {
        setImportResult(`已导入：${r.chunks} 段、提取 ${r.claims} 条观点草稿`
          + `（待审 ${r.stats.pending}、隔离 ${r.stats.quarantined}`
          + `${r.stats.duplicates ? `、疑似重复 ${r.stats.duplicates}` : ''}`
          + `${r.stats.conflicts ? `、疑似冲突 ${r.stats.conflicts}` : ''}）`
          + '——草稿审核通过前不会用于任何建议')
        setContent(''); setTitle('')
        loadClaims()
      })
      .catch((e: ApiError) => setError({ message: e.message, details: e.details }))
  }

  const review = (id: number, decision: 'approve' | 'reject') => {
    api.knowledgeReview(uid, id, decision)
      .then(loadClaims)
      .catch((e: ApiError) => setError({ message: e.message }))
  }

  const pending = (claims || []).filter((c) => c.status === 'pending_review')
  const quarantined = (claims || []).filter((c) => c.status === 'quarantined')

  return (
    <div className="space-y-3">
      <Segmented
        options={[
          { value: 'search', label: '知识检索' },
          { value: 'import', label: '导入知识' },
        ]}
        value={tab} onChange={setTab} />
      {error && <ErrorBox message={error.message} details={error.details} />}

      {tab === 'search' && (
        <>
          <div className="flex gap-2">
            <Input placeholder="搜索全部知识来源（如：平台期 蛋白）"
                   value={q} onChange={(e) => setQ(e.target.value)}
                   onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
            <Button className="shrink-0" disabled={searching} onClick={doSearch}>
              {searching ? '…' : '搜索'}
            </Button>
          </div>
          {searching && <Spinner />}
          {result && result.keywords.length === 0 && (
            <Empty title="没有关键词">关键词太短，换更具体的词试试。</Empty>
          )}
          {result && result.keywords.length > 0 && Object.entries(result.engines).map(([key, engine]) => (
            <Card key={key} title={ENGINE_LABEL[key] || key}
                  right={<Tag>{engine.hits.length} 条</Tag>}>
              {engine.hits.length === 0 && (
                <p className="text-xs leading-relaxed text-muted">
                  {engine.note || '无命中'}
                  {engine.draft_matches ? `（另有 ${engine.draft_matches} 条草稿命中，审核前不展示）` : ''}
                </p>
              )}
              <ul className="rows">
                {engine.hits.map((h, i) => (
                  <li key={i} className="py-2.5 first:pt-0 last:pb-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium">{h.title}</span>
                      <Tag tone={h.provenance.includes('blogger') ? 'blue' : 'neutral'}>
                        {h.provenance}
                      </Tag>
                    </div>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted">{h.snippet}</p>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </>
      )}

      {tab === 'import' && (
        <>
          <Card title="粘贴文本/笔记导入" sub="提取为规则草稿（非模型提炼），全部进入待审核。">
            <Field label="资料标题">
              <Input placeholder="未命名资料" value={title} onChange={(e) => setTitle(e.target.value)} />
            </Field>
            <Textarea className="mt-2.5 min-h-32" placeholder="粘贴文章、笔记或教程内容……"
                      value={content} onChange={(e) => setContent(e.target.value)} />
            <Button className="mt-2.5 w-full" disabled={content.trim().length < 20}
                    onClick={doImport}>
              <Upload size={15} /> 导入并提取观点草稿
            </Button>
            {importResult && <p className="mt-2 text-xs leading-relaxed text-accent-deep">{importResult}</p>}
            <p className="mt-2 text-2xs leading-relaxed text-faint">
              审核通过≠科学验证，高风险内容自动隔离且不可放行。
            </p>
          </Card>

          {pending.length > 0 && (
            <Card title={`待审核观点（${pending.length}）`}>
              <ul className="space-y-2">
                {pending.map((c) => (
                  <li key={c.id} className="rounded-xl border border-line bg-canvas p-3 text-sm leading-relaxed">
                    <div className="flex items-start justify-between gap-2">
                      <p className="flex-1">{c.content}</p>
                      <div className="flex shrink-0 gap-1.5">
                        <button className="tag min-h-8 bg-accent-soft text-accent-deep"
                                onClick={() => review(c.id, 'approve')}>通过</button>
                        <button className="tag min-h-8 bg-red-50 text-red-600"
                                onClick={() => review(c.id, 'reject')}>拒绝</button>
                      </div>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      <Tag>{TYPE_LABEL[c.claim_type] || c.claim_type}</Tag>
                      {c.duplicate_of && (
                        <Tag tone="amber">疑似重复 {c.duplicate_of.ref}（{c.duplicate_of.similarity}）</Tag>
                      )}
                      {c.conflict_with && (
                        <Tag tone="amber">疑似冲突 {c.conflict_with.ref}</Tag>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {quarantined.length > 0 && (
            <Card title={<span className="flex items-center gap-1.5">
              <ShieldAlert size={15} className="text-red-500" /> 已隔离 · 高风险内容（{quarantined.length}）
            </span>}>
              <ul className="space-y-1.5">
                {quarantined.map((c) => (
                  <li key={c.id} className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs
                                            leading-relaxed text-red-700">
                    {c.content}
                    <span className="text-red-600/70">（命中：{c.risk_flag}；不可审核放行，不作为处方依据）</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {claims && pending.length === 0 && quarantined.length === 0 && (
            <Empty icon={<BookOpenText size={20} />} title="暂无待审核观点">
              导入内容后在这里逐条审核。
            </Empty>
          )}

          {proposals.length > 0 && (
            <Card title={`新动作提案（${proposals.length}）待审核入库`}>
              <ul className="space-y-2.5">
                {proposals.map((pr) => (
                  <li key={pr.id} className="rounded-xl border border-line bg-canvas p-3 text-sm">
                    <p className="font-medium">{pr.name}</p>
                    {pr.sentence && <p className="mt-0.5 text-xs text-muted">依据：{pr.sentence}</p>}
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <select id={`pat-${pr.id}`} className="input input-sm !w-28"
                              defaultValue="isolation">
                        {PATTERNS.map((x) => <option key={x}>{x}</option>)}
                      </select>
                      <input id={`eid-${pr.id}`} className="input input-sm !w-44"
                             placeholder="动作 id（英文，如 kettlebell_swing）" />
                      <button className="tag min-h-8 bg-accent-soft text-accent-deep"
                              onClick={async () => {
                                const pattern = (document.getElementById(`pat-${pr.id}`) as HTMLSelectElement).value
                                const exId = (document.getElementById(`eid-${pr.id}`) as HTMLInputElement).value.trim()
                                if (!exId) { setPropNote('请先填写英文动作 id（如 kettlebell_swing）'); return }
                                const res = await fetch(`/api/users/${uid}/exercise-proposals/${pr.id}/review`, {
                                  method: 'POST',
                                  headers: { 'Content-Type': 'application/json',
                                    ...(localStorage.getItem('fc-access-token')
                                      ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {}) },
                                  body: JSON.stringify({ decision: 'approve', pattern, id: exId, link_media: true }),
                                })
                                const body = await res.json()
                                setPropNote(res.ok ? `已入库：${body.exercise_id}（draft，可搜索/可加入计划）` : body.detail?.error || '失败')
                                loadClaims()
                              }}>审核通过并入库</button>
                      <button className="tag min-h-8 bg-red-50 text-red-600"
                              onClick={async () => {
                                await fetch(`/api/users/${uid}/exercise-proposals/${pr.id}/review`, {
                                  method: 'POST',
                                  headers: { 'Content-Type': 'application/json',
                                    ...(localStorage.getItem('fc-access-token')
                                      ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {}) },
                                  body: JSON.stringify({ decision: 'reject' }),
                                })
                                loadClaims()
                              }}>拒绝</button>
                    </div>
                  </li>
                ))}
              </ul>
              {propNote && <p className="mt-2 text-xs text-accent-deep">{propNote}</p>}
              <p className="mt-2 text-2xs leading-relaxed text-faint">
                入库动作 status=draft（结构化属性未审核）；伤病用户的计划筛选不会依赖其空压力数据。
              </p>
            </Card>
          )}

          <VideoImportPanel uid={uid} />
        </>
      )}
    </div>
  )
}


// ---- M3.2：视频导入（上传→候选确认→关联/新建/忽略）----
interface MediaAsset {
  id: number
  title: string
  status: string
  error: string | null
  created_at: string
  candidates: {
    exercise_id: string; name: string; match: string; sentence: string
    start: number; status: string
  }[]
}

export function VideoImportPanel({ uid }: { uid: string }) {
  const [assets, setAssets] = useState<MediaAsset[] | null>(null)
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  // M5.2 P0-3：三步上传（选视频→可选字幕→点解析），不再选择即传
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [subtitleFile, setSubtitleFile] = useState<File | null>(null)
  const [manualFor, setManualFor] = useState<number | null>(null)
  const [manual, setManual] = useState({ name: '', aliases: '', pattern: 'isolation' })
  const [manualNote, setManualNote] = useState('')

  const load = useCallback(() => {
    fetch(`/api/users/${uid}/media/videos`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    })
      .then((r) => r.json())
      .then((r) => setAssets(r.assets as MediaAsset[]))
      .catch(() => setAssets([]))
  }, [uid])
  useEffect(() => { load() }, [load])

  const upload = async (video: File | null, subtitle: File | null) => {
    if (!video) { setNote('请先选择视频文件'); return }
    setBusy(true); setNote('')
    const form = new FormData()
    form.append('title', title || video.name)
    form.append('video', video)
    if (subtitle) form.append('subtitle', subtitle)
    const res = await fetch(`/api/users/${uid}/media/videos`, {
      method: 'POST',
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
      body: form,
    })
    const body = await res.json()
    if (!res.ok) { setNote(body.detail?.error || '上传失败'); setBusy(false); return }
    setNote('已上传，后台处理中（字幕直读或本地转写）…')
    for (let i = 0; i < 15; i++) {       // 轮询任务状态
      await new Promise((r) => setTimeout(r, 2000))
      load()
      const done = (assets ?? []).length // 简单触发刷新
      if (done >= 0) { /* 状态由渲染呈现 */ }
      const list = await fetch(`/api/users/${uid}/media/videos`, {
        headers: localStorage.getItem('fc-access-token')
          ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
      }).then((r) => r.json())
      const me = (list.assets as MediaAsset[]).find((a) => a.id === body.asset_id)
      if (me && me.status !== 'processing') { setNote(''); break }
    }
    setBusy(false); setVideoFile(null); setSubtitleFile(null); load()
  }

  const createManualProposal = (assetId: number) => {
    fetch(`/api/users/${uid}/media/${assetId}/manual-proposal`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('fc-access-token')
          ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {}),
      },
      body: JSON.stringify({
        name: manual.name,
        aliases: manual.aliases.split(/[、,，]/).map((x) => x.trim()).filter(Boolean),
        pattern: manual.pattern,
      }),
    }).then(async (r) => {
      const body = await r.json()
      if (!r.ok) { setManualNote(body.detail?.error || '创建失败'); return }
      setManualNote(`提案 #${body.proposal_id} 已创建——在上方"新动作提案"卡审核入库`)
      setManualFor(null); setManual({ name: '', aliases: '', pattern: 'isolation' })
    })
  }

  const confirm = async (assetId: number, index: number, action: string) => {
    const res = await fetch(`/api/users/${uid}/media/${assetId}/candidates/${index}/confirm`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('fc-access-token')
          ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {}),
      },
      body: JSON.stringify({ action }),
    })
    const body = await res.json()
    if (!res.ok) setNote(body.detail?.error || '操作失败')
    load()
  }

  return (
    <Card title="视频导入" sub="可选：先选字幕再解析；无字幕时服务器本地转写（较慢）。识别不强行匹配：无候选时如实显示。">
      <Input className="mb-2.5" placeholder="视频标题（如：深蹲教学）"
             value={title} onChange={(e) => setTitle(e.target.value)} />
      <div className="space-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-xs text-muted">① 视频</span>
          <input type="file" disabled={busy} accept="video/mp4,video/webm,video/quicktime,.mkv"
                 className="w-full text-xs text-muted file:mr-2 file:rounded-lg file:border-0
                            file:bg-canvas file:px-2.5 file:py-1.5 file:text-xs file:font-medium file:text-ink"
                 onChange={(e) => setVideoFile(e.target.files?.[0] || null)} />
          {videoFile && <span className="shrink-0 text-xs text-accent-deep">{videoFile.name}</span>}
        </div>
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-xs text-muted">② 字幕</span>
          <input type="file" accept=".srt,.vtt" disabled={busy}
                 className="w-full text-xs text-muted file:mr-2 file:rounded-lg file:border-0
                            file:bg-canvas file:px-2.5 file:py-1.5 file:text-xs file:font-medium file:text-ink"
                 onChange={(e) => setSubtitleFile(e.target.files?.[0] || null)} />
          {subtitleFile && <span className="shrink-0 text-xs text-accent-deep">{subtitleFile.name}</span>}
        </div>
        <Button className="w-full" disabled={busy || !videoFile}
                onClick={() => upload(videoFile, subtitleFile)}>
          ③ 开始解析{subtitleFile ? '（视频+字幕）' : '（无字幕，本地转写较慢）'}
        </Button>
      </div>
      {note && <p className="mt-2 text-xs text-accent-deep">{note}</p>}

      {(assets || []).map((a) => (
        <div key={a.id} className="mt-3 rounded-xl border border-line bg-canvas p-3">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{a.title}</span>
            <Tag tone={a.status === 'ready' ? 'green' : a.status === 'failed' ? 'red' : 'amber'}>
              {{ ready: '已处理', failed: '失败', processing: '处理中' }[a.status] || a.status}
            </Tag>
          </div>
          {a.error && <p className="mt-1 text-xs text-red-600">{a.error}</p>}
          {a.status === 'ready' && (a.candidates.length === 0
            ? (<div className="mt-1.5 text-xs">
                 <p className="text-muted">未识别到库内动作候选——可以手动创建新动作提案：</p>
                 {manualFor === a.id ? (
                   <div className="mt-2 space-y-2 rounded-xl border border-line bg-surface p-3">
                     <Input className="input-sm" placeholder="动作名称（必填）"
                            value={manual.name}
                            onChange={(e) => setManual({ ...manual, name: e.target.value })} />
                     <Input className="input-sm" placeholder="别名（顿号分隔，可选）"
                            value={manual.aliases}
                            onChange={(e) => setManual({ ...manual, aliases: e.target.value })} />
                     <select className="input input-sm" value={manual.pattern}
                             onChange={(e) => setManual({ ...manual, pattern: e.target.value })}>
                       {PATTERNS.map((x) => <option key={x}>{x}</option>)}
                     </select>
                     <div className="flex gap-2">
                       <Button className="flex-1" disabled={!manual.name.trim()}
                               onClick={() => createManualProposal(a.id)}>创建提案</Button>
                       <Button variant="ghost" className="flex-1"
                               onClick={() => setManualFor(null)}>取消</Button>
                     </div>
                   </div>
                 ) : (
                   <button className="mt-1 font-medium text-accent-deep hover:underline"
                           onClick={() => { setManualFor(a.id); setManualNote('') }}>手动创建动作提案</button>
                 )}
                 {manualNote && <p className="mt-1 text-accent-deep">{manualNote}</p>}
               </div>)
            : a.candidates.map((c, i) => (
              <div key={i} className="mt-2 rounded-xl border border-line bg-surface p-2.5 text-xs leading-relaxed">
                <p className="text-ink">
                  {c.name}
                  <span className="ml-1 text-muted">（{c.match} 匹配 @ {Math.round(c.start)}s）</span>
                  {c.status !== 'pending' && <Tag className="ml-1.5">{c.status}</Tag>}
                </p>
                <p className="mt-0.5 text-muted">"{c.sentence}"</p>
                {c.status === 'pending' && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <button className="tag min-h-8 bg-accent-soft text-accent-deep"
                            onClick={() => confirm(a.id, i, 'link')}>关联该动作</button>
                    <button className="tag min-h-8 bg-sky-50 text-sky-700"
                            onClick={() => confirm(a.id, i, 'new')}>新动作候选</button>
                    <button className="tag min-h-8 border border-line bg-surface text-muted"
                            onClick={() => confirm(a.id, i, 'reject')}>忽略</button>
                  </div>
                )}
              </div>
            )))}
        </div>
      ))}
    </Card>
  )
}
