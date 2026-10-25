import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CalendarDays, ChevronLeft, ChevronRight, CheckCircle2, CircleDashed,
  Plus, UtensilsCrossed,
} from 'lucide-react'
import { api, ApiError } from '../api'
import { ErrorBox, Notice, Spinner } from '../components/Bits'
import FoodPicker from './nutrition/FoodPicker'
import MealEditor from './nutrition/MealEditor'
import RecipeSheet from './nutrition/RecipeSheet'
import { useApp } from '../store'
import type { DayNutrition, MealType, NutritionTargets } from '../types'
import { MEAL_LABEL, MEAL_ORDER, fmtNutrient, itemLine,
         shiftDate, todayISO } from '../lib/nutrition'

export default function Nutrition() {
  const uid = useApp((s) => s.uid)
  const [day, setDay] = useState(todayISO())
  const [data, setData] = useState<DayNutrition | null>(null)
  const [targets, setTargets] = useState<NutritionTargets | null>(null)
  const [error, setError] = useState('')
  const [picking, setPicking] = useState<MealType | null>(null)
  const [editing, setEditing] = useState<DayNutrition['meals'][number] | null>(null)
  const [recipesOpen, setRecipesOpen] = useState(false)

  const load = useCallback(() => {
    Promise.all([
      api.dayNutrition(uid, day),
      api.nutritionTargets(uid).then((r) => r.targets).catch(() => null),
    ]).then(([d, t]) => { setData(d); setTargets(t) })
      .catch((e) => setError((e as ApiError).message))
  }, [uid, day])
  useEffect(load, [load])

  const totals = data?.day.totals
  const pct = (v: number | null | undefined, t: number | null | undefined) =>
    v != null && t ? Math.round((v / t) * 100) : null

  const mealsByType = useMemo(() => {
    const map: Partial<Record<MealType, DayNutrition['meals']>> = {}
    for (const m of data?.meals ?? []) {
      (map[m.meal_type] = map[m.meal_type] ?? []).push(m)
    }
    return map
  }, [data])

  if (error) return <div className="pt-4"><ErrorBox message={error} onRetry={load} /></div>
  if (!data) return <Spinner />

  return (
    <div className="mx-auto w-full max-w-5xl">
      {/* 日期导航 */}
      <div className="mb-3 flex items-center justify-between gap-2">
        <button className="btn btn-ghost size-9 p-0" aria-label="前一天"
                onClick={() => setDay(shiftDate(day, -1))}><ChevronLeft size={18} /></button>
        <div className="text-center">
          <p className="text-[15px] font-bold">
            {day === todayISO() ? '今天' : day.slice(5).replace('-', ' 月 ') + ' 日'}
          </p>
          <p className="text-2xs text-muted">{day}</p>
        </div>
        <button className="btn btn-ghost size-9 p-0" aria-label="后一天" disabled={day >= todayISO()}
                onClick={() => setDay(shiftDate(day, 1))}><ChevronRight size={18} /></button>
      </div>

      {/* 已记录汇总 vs 目标 */}
      <div className="card !p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">已记录摄入</p>
          <button className="btn btn-ghost text-xs" onClick={async () => {
            await api.copyDayMeals(uid, shiftDate(day, -1), day); load()
          }}>
            <CalendarDays size={14} /> 复制昨天
          </button>
        </div>
        <div className="mt-3 grid grid-cols-4 gap-2 text-center">
          {([['能量', totals?.energy_kcal, targets?.energy_kcal, 'kcal'],
             ['蛋白质', totals?.protein_g, targets?.protein_g, 'g'],
             ['碳水', totals?.carbohydrate_g, targets?.carbohydrate_g, 'g'],
             ['脂肪', totals?.fat_g, targets?.fat_g, 'g']] as const).map(
            ([label, v, t, unit]) => {
              const p = pct(v, t)
              return (
                <div key={label} className="rounded-xl bg-canvas p-2">
                  <p className="text-2xs text-muted">{label}{t ? ` · 目标 ${t}${unit}` : ''}</p>
                  <p className="nums mt-0.5 text-lg font-bold">{fmtNutrient(v)}</p>
                  {p != null
                    ? <p className={`text-2xs font-medium ${
                        p > 130 ? 'text-amber-700' : p >= 70 ? 'text-emerald-700' : 'text-muted'}`}>
                        {p}%
                      </p>
                    : <p className="text-2xs text-faint">{targets ? '' : '未设目标'}</p>}
                </div>
              )
            })}
        </div>
        {/* 记录完整标记（影响分析口径：只有完整日才做方向性比较） */}
        <button className="mt-3 flex w-full items-center gap-2 rounded-xl bg-canvas p-2.5
                           text-left text-xs leading-relaxed"
                onClick={async () => {
                  await api.setDayComplete(uid, day, !data.complete_mark); load()
                }}>
          {data.complete_mark
            ? <CheckCircle2 size={16} className="shrink-0 text-emerald-600" />
            : <CircleDashed size={16} className="shrink-0 text-muted" />}
          <span className="text-muted">
            {data.complete_mark
              ? '已标记：今天的饮食记录完整（分析将基于全天口径）'
              : '未标记完整：以下为已记录摄入量，不代表全天总摄入；记全后点这里标记'}
          </span>
        </button>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <Link to="/nutrition/targets" className="font-medium text-accent-deep hover:underline">
          营养目标与偏好
        </Link>
        <div className="flex gap-3">
          <Link to="/experts/nutrition" className="font-medium text-accent-deep hover:underline">
            营养顾问工作台
          </Link>
          <Link to="/nutrition/history" className="font-medium text-accent-deep hover:underline">
            趋势
          </Link>
        </div>
      </div>

      {/* 四个餐次 */}
      <div className="mt-4 space-y-3">
        {MEAL_ORDER.map((mt) => {
          const meals = mealsByType[mt] ?? []
          const kcal = meals.reduce((n, m) => n + (m.totals.energy_kcal || 0), 0)
          return (
            <div key={mt} className="card">
              <div className="flex items-center justify-between">
                <p className="text-[15px] font-semibold">{MEAL_LABEL[mt]}</p>
                <span className="nums text-xs text-muted">
                  {meals.length ? `${Math.round(kcal)} kcal` : '未记录'}
                </span>
              </div>
              {meals.length === 0 ? (
                <button className="mt-2 flex w-full items-center justify-center gap-1.5
                                   rounded-xl border border-dashed border-lineStrong py-2.5
                                   text-xs font-medium text-muted transition-colors
                                   hover:border-accent-deep/40 hover:text-ink"
                        onClick={() => setPicking(mt)}>
                  <Plus size={14} /> 记录{MEAL_LABEL[mt]}
                </button>
              ) : (
                <>
                  <ul className="mt-1 divide-y divide-line">
                    {meals.map((meal) => (
                      <li key={meal.id}>
                        {meal.items.map((item, i) => (
                          <p key={i} className="flex items-center justify-between gap-2
                                               py-1.5 text-[13px]">
                            <span className="min-w-0 truncate">
                              {itemLine(item)}
                              {item.snapshot_meta?.verified_status === 'user_created'
                                && <span className="ml-1 text-2xs text-faint">（自录）</span>}
                            </span>
                          </p>
                        ))}
                        <div className="flex items-center justify-between gap-2 pb-2">
                          <span className="text-2xs text-faint">
                            小计 {fmtNutrient(meal.totals.energy_kcal)} kcal ·
                            蛋白 {fmtNutrient(meal.totals.protein_g)}g
                            {meal.notes ? ` · ${meal.notes}` : ''}
                          </span>
                          <button className="btn btn-ghost text-2xs text-accent-deep"
                                  onClick={() => setEditing(meal)}>编辑</button>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <button className="mt-1 flex w-full items-center justify-center gap-1.5
                                     rounded-xl py-1.5 text-xs font-medium text-muted
                                     hover:text-ink"
                          onClick={() => setPicking(mt)}>
                    <Plus size={13} /> 再加一条
                  </button>
                </>
              )}
            </div>
          )
        })}
      </div>

      {/* 食谱 */}
      <button className="card mt-3 flex w-full items-center gap-3 text-left"
              onClick={() => setRecipesOpen(true)}>
        <span className="flex size-9 items-center justify-center rounded-xl bg-accent-soft">
          <UtensilsCrossed size={17} className="text-accent-deep" />
        </span>
        <span className="flex-1 text-sm font-medium">常用食谱（保存一整餐，一键复用）</span>
      </button>

      <Notice tone="amber" className="mt-3">
        数值为「已记录摄入量」；食物营养来自内置参考值或你录入的标签（约值，非实验室测定），
        未知项保持缺失不按 0 计。
      </Notice>

      {picking && (
        <FoodPicker mealType={picking} date={day}
                    onClose={() => setPicking(null)} onSaved={load} />
      )}
      {editing && (
        <MealEditor meal={editing} date={day} onClose={() => { setEditing(null); load() }} />
      )}
      <RecipeSheet open={recipesOpen} date={day}
                   onClose={() => setRecipesOpen(false)} onUsed={load} />
    </div>
  )
}
