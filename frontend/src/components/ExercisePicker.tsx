import { useEffect, useState } from 'react'
import { api } from '../api'
import { ExerciseSummary } from '../types'
import { ErrorBox, Spinner } from './Bits'

// 动作选择器：搜索 + 肌群筛选。选择结果只给官方名，校验在后端。
export default function ExercisePicker({ onPick, onClose }: {
  onPick: (ex: ExerciseSummary) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const [muscle, setMuscle] = useState('')
  const [items, setItems] = useState<ExerciseSummary[] | null>(null)
  const [error, setError] = useState('')

  const MUSCLES = ['chest', 'back', 'shoulders', 'biceps', 'triceps',
    'quads', 'hamstrings', 'glutes', 'calves', 'core']

  useEffect(() => {
    const t = setTimeout(() => {
      api.exercises({ q, muscle })
        .then((r) => setItems(r.exercises))
        .catch((e) => setError(e.message))
    }, 200)
    return () => clearTimeout(t)
  }, [q, muscle])

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/70" onClick={onClose}>
      <div className="max-h-[80vh] w-full overflow-y-auto rounded-t-2xl bg-neutral-900 p-4"
           onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-semibold">选择动作</h3>
          <button className="text-neutral-400" onClick={onClose}>关闭</button>
        </div>
        <input className="input mb-2" placeholder="搜索名称/别名" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <div className="mb-3 flex gap-1.5 overflow-x-auto pb-1">
          <button onClick={() => setMuscle('')}
                  className={`tag shrink-0 ${!muscle ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-300'}`}>
            全部
          </button>
          {MUSCLES.map((m) => (
            <button key={m} onClick={() => setMuscle(m)}
                    className={`tag shrink-0 ${muscle === m ? 'bg-accent text-neutral-950' : 'bg-neutral-800 text-neutral-300'}`}>
              {m}
            </button>
          ))}
        </div>
        {error && <ErrorBox message={error} />}
        {!items && !error && <Spinner />}
        {items?.length === 0 && <p className="py-6 text-center text-sm text-neutral-500">没有匹配的动作</p>}
        <ul className="divide-y divide-neutral-800">
          {items?.map((ex) => (
            <li key={ex.id}>
              <button className="flex w-full items-center justify-between py-3 text-left"
                      onClick={() => { onPick(ex); onClose() }}>
                <div>
                  <span className="text-sm">{ex.name}</span>
                  <span className="ml-2 text-xs text-neutral-500">{ex.pattern}</span>
                </div>
                {ex.status !== 'approved' && (
                  <span className="tag bg-amber-900/60 text-amber-300">未审核</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
