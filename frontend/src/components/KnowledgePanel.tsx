// M3 知识库面板：统一检索（md/博主观点/教练卡/我的导入）+ 导入 + 待审核
import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, Empty, ErrorBox, Spinner, Tag } from './Bits'

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

  const loadClaims = useCallback(() => {
    api.knowledgeClaims(uid)
      .then((r) => setClaims((r.claims as unknown as ImportedClaim[])))
      .catch(() => setClaims([]))
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
      <div className="flex gap-2">
        <button onClick={() => setTab('search')}
                className={`btn flex-1 ${tab === 'search' ? 'bg-accent text-neutral-950' : 'bg-neutral-800'}`}>
          知识检索
        </button>
        <button onClick={() => setTab('import')}
                className={`btn flex-1 ${tab === 'import' ? 'bg-accent text-neutral-950' : 'bg-neutral-800'}`}>
          导入知识
        </button>
      </div>
      {error && <ErrorBox message={error.message} details={error.details} />}

      {tab === 'search' && (
        <>
          <div className="flex gap-2">
            <input className="input" placeholder="搜索全部知识来源（如：平台期 蛋白）"
                   value={q} onChange={(e) => setQ(e.target.value)}
                   onKeyDown={(e) => e.key === 'Enter' && doSearch()} />
            <button className="btn-primary shrink-0" disabled={searching} onClick={doSearch}>
              {searching ? '…' : '搜索'}
            </button>
          </div>
          {searching && <Spinner />}
          {result && result.keywords.length === 0 && (
            <Empty>关键词太短，换更具体的词试试</Empty>
          )}
          {result && result.keywords.length > 0 && Object.entries(result.engines).map(([key, engine]) => (
            <Card key={key} title={ENGINE_LABEL[key] || key}
                  right={<Tag>{engine.hits.length} 条</Tag>}>
              {engine.hits.length === 0 && (
                <p className="text-xs text-neutral-500">
                  {engine.note || '无命中'}
                  {engine.draft_matches ? `（另有 ${engine.draft_matches} 条草稿命中，审核前不展示）` : ''}
                </p>
              )}
              <ul className="space-y-2">
                {engine.hits.map((h, i) => (
                  <li key={i} className="text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium">{h.title}</span>
                      <Tag tone={h.provenance.includes('blogger') ? 'blue' : 'neutral'}>
                        {h.provenance}
                      </Tag>
                    </div>
                    <p className="text-xs text-neutral-400">{h.snippet}</p>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </>
      )}

      {tab === 'import' && (
        <>
          <Card title="粘贴文本/笔记导入">
            <input className="input mb-2" placeholder="资料标题" value={title}
                   onChange={(e) => setTitle(e.target.value)} />
            <textarea className="input min-h-32" placeholder="粘贴文章、笔记或教程内容……"
                      value={content} onChange={(e) => setContent(e.target.value)} />
            <button className="btn-primary mt-2 w-full" disabled={content.trim().length < 20}
                    onClick={doImport}>导入并提取观点草稿</button>
            {importResult && <p className="mt-2 text-xs text-accent">{importResult}</p>}
            <p className="mt-2 text-[11px] leading-relaxed text-neutral-500">
              提取为规则草稿（非模型提炼），全部进入待审核；审核通过≠科学验证，
              高风险内容自动隔离且不可放行。
            </p>
          </Card>

          {pending.length > 0 && (
            <Card title={`待审核观点（${pending.length}）`}>
              <ul className="space-y-2">
                {pending.map((c) => (
                  <li key={c.id} className="rounded-lg bg-neutral-800/60 p-2.5 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <p className="flex-1">{c.content}</p>
                      <div className="flex shrink-0 gap-1.5">
                        <button className="tag bg-emerald-900/60 text-emerald-300"
                                onClick={() => review(c.id, 'approve')}>通过</button>
                        <button className="tag bg-red-900/60 text-red-300"
                                onClick={() => review(c.id, 'reject')}>拒绝</button>
                      </div>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-1.5">
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
            <Card title={<span><Tag tone="red">已隔离</Tag> <span className="ml-1">高风险内容（{quarantined.length}）</span></span>}>
              <ul className="space-y-1.5">
                {quarantined.map((c) => (
                  <li key={c.id} className="rounded-lg bg-red-950/30 p-2 text-xs text-red-300">
                    {c.content}
                    <span className="ml-1">（命中：{c.risk_flag}；不可审核放行，不作为处方依据）</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {claims && pending.length === 0 && quarantined.length === 0 && (
            <Empty>暂无待审核观点；导入内容后在这里逐条审核。</Empty>
          )}
        </>
      )}
    </div>
  )
}
