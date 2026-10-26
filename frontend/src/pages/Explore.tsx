import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { api } from '../api'
import {
  Chip, Empty, ErrorBox, PageHeader, Segmented, Spinner, Tag,
} from '../components/Bits'
import { ExerciseCover } from '../components/media'
import KnowledgePanel from '../components/KnowledgePanel'
import { ExerciseSummary, LocationsResponse } from '../types'
import { useApp } from '../store'

const MUSCLES = ['chest', 'back', 'shoulders', 'biceps', 'triceps',
  'quads', 'hamstrings', 'glutes', 'calves', 'core']

const MUSCLE_LABEL: Record<string, string> = {
  chest: '胸', back: '背', shoulders: '肩', biceps: '二头', triceps: '三头',
  quads: '股四头', hamstrings: '腘绳', glutes: '臀', calves: '小腿', core: '核心',
}

export const PATTERN_LABEL: Record<string, string> = {
  squat: '蹲', hinge: '髋铰链', lunge: '弓步', h_push: '水平推', v_push: '垂直推',
  h_pull: '水平拉', v_pull: '垂直拉', isolation: '孤立', core: '核心',
  carry: '负重行走', cardio: '有氧',
}
const LOCATION_LABEL: Record<string, string> = {
  gym: '健身房', home: '居家', outdoor: '户外',
}

export default function Explore() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [pane, setPane] = useState<'exercises' | 'knowledge'>('exercises')
  const [q, setQ] = useState('')
  const [muscle, setMuscle] = useState('')
  const [pattern, setPattern] = useState('')
  const [equipment, setEquipment] = useState('')
  const [location, setLocation] = useState('')
  const [availableOnly, setAvailableOnly] = useState(false)
  const [frequentOnly, setFrequentOnly] = useState(false)
  const [places, setPlaces] = useState<LocationsResponse | null>(null)
  const [items, setItems] = useState<ExerciseSummary[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.locations(uid).then(setPlaces).catch(() => setPlaces(null))
  }, [uid])

  useEffect(() => {
    const t = setTimeout(() => {
      const current = places?.locations.find((x) => x.id === places.current_id)
      api.exercises({
        uid, q, muscle, pattern, equipment, location,
        ...(current ? { location_id: current.id } : {}),
        available: availableOnly, frequent: frequentOnly,
      })
        .then((r) => { setItems(r.exercises); setError('') })
        .catch((e) => setError(e.message))
    }, 200)
    return () => clearTimeout(t)
  }, [q, muscle, pattern, equipment, location, availableOnly, frequentOnly,
      places, uid])

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

          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <select className="input input-sm" aria-label="动作模式"
                    value={pattern} onChange={(e) => setPattern(e.target.value)}>
              <option value="">全部动作模式</option>
              {Object.entries(PATTERN_LABEL).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
            <select className="input input-sm" aria-label="器械筛选"
                    value={equipment} onChange={(e) => setEquipment(e.target.value)}>
              <option value="">全部器械</option>
              {places?.equipment.filter((x) =>
                x.scope === 'system' && x.id !== 'bodyweight').map((eq) => (
                  <option key={eq.id} value={eq.id}>{eq.name}</option>
                ))}
            </select>
            <select className="input input-sm" aria-label="地点类型"
                    value={location} onChange={(e) => setLocation(e.target.value)}>
              <option value="">全部地点类型</option>
              {Object.entries(LOCATION_LABEL).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
            </select>
            <div className="flex gap-1.5">
              <Chip active={availableOnly}
                    onClick={() => {
                      if (!places?.current_id) { setError('请先在“我的 → 训练地点与器械”设置当前地点'); return }
                      setAvailableOnly(!availableOnly)
                    }}>
                仅可执行
              </Chip>
              <Chip active={frequentOnly}
                    onClick={() => setFrequentOnly(!frequentOnly)}>
                常用
              </Chip>
            </div>
          </div>
          <p className="mt-1.5 text-2xs text-faint">
            “仅可执行”按当前地点
            {places?.locations.find((x) => x.id === places.current_id)?.name || '（未设置）'}
            的器械配置判断。
          </p>

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
                    <p className="mt-auto flex flex-wrap items-center gap-1 pt-1.5 text-2xs text-faint">
                      {ex.equipment_names?.length
                        ? ex.equipment_names.join(' / ') : '自重'}
                      {ex.frequent && <Tag tone="brand">常用</Tag>}
                      {ex.available === false && (
                        <Tag tone="amber">
                          缺{ex.missing_equipment?.join('/') || '器械'}
                        </Tag>
                      )}
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
