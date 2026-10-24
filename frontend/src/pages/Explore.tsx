import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api'
import {
  Chip, Empty, ErrorBox, PageHeader, Segmented, Spinner, Tag,
} from '../components/Bits'
import { ExerciseCover } from '../components/media'
import KnowledgePanel from '../components/KnowledgePanel'
import { ExerciseSummary } from '../types'
import { useApp } from '../store'

const MUSCLES = ['chest', 'back', 'shoulders', 'biceps', 'triceps',
  'quads', 'hamstrings', 'glutes', 'calves', 'core']

const MUSCLE_LABEL: Record<string, string> = {
  chest: '胸', back: '背', shoulders: '肩', biceps: '二头', triceps: '三头',
  quads: '股四头', hamstrings: '腘绳', glutes: '臀', calves: '小腿', core: '核心',
}

export const PATTERN_LABEL: Record<string, string> = {
  squat: '蹲', hinge: '髋铰链', lunge: '弓步', h_push: '水平推', v_push: '垂直推',
  h_pull: '水平拉', v_pull: '垂直拉', isolation: '孤立', core: '核心', carry: '负重行走',
}

export default function Explore() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [pane, setPane] = useState<'exercises' | 'knowledge'>('exercises')
  const [q, setQ] = useState('')
  const [muscle, setMuscle] = useState('')
  const [items, setItems] = useState<ExerciseSummary[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      api.exercises({ q, muscle })
        .then((r) => setItems(r.exercises))
        .catch((e) => setError(e.message))
    }, 200)
    return () => clearTimeout(t)
  }, [q, muscle])

  const openDetail = useCallback((id: string) => {
    navigate(`/explore/${encodeURIComponent(id)}`)
  }, [navigate])

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader title="探索" sub="动作库与统一知识库（文件/博主观点/教练卡/我的导入）" />

      <Segmented
        options={[
          { value: 'exercises', label: '动作库' },
          { value: 'knowledge', label: '知识库' },
        ]}
        value={pane} onChange={setPane} className="mb-4" />

      {pane === 'knowledge' ? <KnowledgePanel uid={uid} /> : (
        <>
          {/* 搜索 */}
          <div className="relative">
            <Search size={17} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input className="input !pl-10" placeholder="搜索名称或别名" value={q}
                   onChange={(e) => setQ(e.target.value)} />
          </div>

          {/* 肌群筛选 */}
          <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0">
            <Chip active={!muscle} onClick={() => setMuscle('')}>全部</Chip>
            {MUSCLES.map((m) => (
              <Chip key={m} active={muscle === m} onClick={() => setMuscle(m)}>
                {MUSCLE_LABEL[m] || m}
              </Chip>
            ))}
          </div>

          {error && <div className="mt-3"><ErrorBox message={error} /></div>}
          {!items && !error && <Spinner />}
          {items?.length === 0 && (
            <div className="mt-4">
              <Empty title="没有匹配的动作">换个关键词，或清除筛选条件试试。</Empty>
            </div>
          )}
          {items && items.length > 0 && (
            <p className="nums mt-3 text-xs text-muted">共 {items.length} 个动作 · 含教学要点与关节压力标注</p>
          )}

          {/* 动作卡片 */}
          <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items?.map((ex) => (
              <li key={ex.id}>
                <button className="card flex h-full w-full gap-3.5 text-left transition-shadow hover:shadow-pop"
                        onClick={() => openDetail(ex.id)}>
                  <ExerciseCover uid={uid} exerciseId={ex.id} name={ex.name}
                                 className="size-18 h-[72px] w-[72px] shrink-0 rounded-xl" iconSize={24} />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 truncate text-[15px] font-semibold">{ex.name}</p>
                      {ex.status === 'approved'
                        ? <Tag tone="green" className="shrink-0">已审核</Tag>
                        : <Tag tone="amber" className="shrink-0">未审核</Tag>}
                    </div>
                    <p className="mt-0.5 text-xs text-muted">
                      {PATTERN_LABEL[ex.pattern] || ex.pattern}
                      {ex.primary.length > 0 && ` · ${ex.primary.map((m) => MUSCLE_LABEL[m] || m).join('、')}`}
                    </p>
                    <p className="mt-auto pt-1.5 text-2xs text-faint">
                      {ex.equipment.length > 0 ? ex.equipment.join(' / ') : '自重'}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
