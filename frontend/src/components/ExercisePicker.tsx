import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { ExerciseSummary } from '../types'
import { Chip, Empty, ErrorBox, Sheet, Spinner } from './Bits'
import { ExerciseCover } from './media'

const MUSCLES = ['chest', 'back', 'shoulders', 'biceps', 'triceps',
  'quads', 'hamstrings', 'glutes', 'calves', 'core']
const MUSCLE_LABEL: Record<string, string> = {
  chest: '胸', back: '背', shoulders: '肩', biceps: '二头', triceps: '三头',
  quads: '股四头', hamstrings: '腘绳', glutes: '臀', calves: '小腿', core: '核心',
}

// 动作选择器：搜索 + 肌群筛选。选择结果只给官方名，校验在后端。
export default function ExercisePicker({ onPick, onClose, uid }: {
  onPick: (ex: ExerciseSummary) => void
  onClose: () => void
  uid?: string
}) {
  const [q, setQ] = useState('')
  const [muscle, setMuscle] = useState('')
  const [items, setItems] = useState<ExerciseSummary[] | null>(null)
  const [error, setError] = useState('')
  const me = uid || ''

  useEffect(() => {
    const t = setTimeout(() => {
      fetch(`/api/exercises?q=${encodeURIComponent(q)}${muscle ? `&muscle=${muscle}` : ''}` + (me ? `&uid=${encodeURIComponent(me)}` : ''), {
        headers: localStorage.getItem('fc-access-token')
          ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
      })
        .then((r) => r.json()).then((r) => setItems(r.exercises))
        .catch((e) => setError(e.message))
    }, 200)
    return () => clearTimeout(t)
  }, [q, muscle, me])

  return (
    <Sheet open onClose={onClose} title="选择动作" wide>
      <div className="relative mb-3">
        <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
        <input className="input !pl-10" placeholder="搜索名称/别名" value={q}
               onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="-mx-4 mb-3 flex gap-2 overflow-x-auto px-4 pb-1">
        <Chip active={!muscle} onClick={() => setMuscle('')}>全部</Chip>
        {MUSCLES.map((m) => (
          <Chip key={m} active={muscle === m} onClick={() => setMuscle(m)}>{MUSCLE_LABEL[m] || m}</Chip>
        ))}
      </div>

      {error && <ErrorBox message={error} />}
      {!items && !error && <Spinner />}
      {items?.length === 0 && <Empty title="没有匹配的动作">换个关键词试试。</Empty>}
      <ul className="rows -mx-4">
        {items?.map((ex) => (
          <li key={ex.id}>
            <button className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-canvas"
                    onClick={() => { onPick({ ...ex, measurement: ex.measurement }); onClose() }}>
              <ExerciseCover uid={me} exerciseId={ex.id} name={ex.name}
                             className="size-11 shrink-0 rounded-lg" iconSize={16} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{ex.name}</p>
                <p className="truncate text-xs text-muted">{ex.pattern}{ex.primary.length ? ` · ${ex.primary.join('、')}` : ''}</p>
              </div>
              {ex.status !== 'approved' && (
                <span className="tag shrink-0 bg-amber-50 text-amber-700">未审核</span>
              )}
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  )
}
