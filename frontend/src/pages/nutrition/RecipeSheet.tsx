import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, Sheet } from '../../components/Bits'
import { useApp } from '../../store'
import type { DayNutrition, Recipe } from '../../types'
import { fmtNutrient, itemLine } from '../../lib/nutrition'

/** 食谱：把最近一餐存为食谱 / 一键把食谱加为今天的一餐（快照复用） */
export default function RecipeSheet({ open, date, onClose, onUsed }:
  { open: boolean; date: string; onClose: () => void; onUsed: () => void }) {
  const uid = useApp((s) => s.uid)
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [day, setDay] = useState<DayNutrition | null>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.recipes(uid).then((r) => setRecipes(r.recipes)).catch(() => {})
    api.dayNutrition(uid, date).then(setDay).catch(() => setDay(null))
  }, [uid, date])
  useEffect(() => { if (open) load() }, [open, load])

  async function saveFromMeal(mealId: number) {
    const meal = day?.meals.find((m) => m.id === mealId)
    if (!meal) return
    setBusy(true); setError('')
    try {
      await api.saveRecipe(uid, {
        name: name.trim() || `${meal.items[0]?.food_name ?? '餐'}组合`,
        items: meal.items.map((it) => ({ food_id: it.food_id, amount: it.amount, unit: it.unit })),
      })
      setName(''); load()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  async function apply(recipeId: number) {
    const recipe = recipes.find((r) => r.id === recipeId)
    if (!recipe) return
    setBusy(true); setError('')
    try {
      await api.saveMeal(uid, {
        date, meal_type: 'snack',
        items: recipe.items.map((it) => ({ food_id: it.food_id, amount: it.amount, unit: it.unit })),
        notes: `食谱：${recipe.name}`,
      })
      onUsed(); onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open={open} title="常用食谱" onClose={onClose}>
      {error && <div className="mb-2"><ErrorBox message={error} /></div>}
      {recipes.length === 0 ? (
        <p className="py-2 text-sm leading-relaxed text-muted">
          还没有食谱。先记录一餐，然后在这里把它保存成食谱；以后一键整餐复用。
        </p>
      ) : (
        <ul className="space-y-2">
          {recipes.map((r) => (
            <li key={r.id} className="rounded-xl border border-line p-2.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold">{r.name}</p>
                <div className="flex gap-1">
                  <Button size="sm" disabled={busy} onClick={() => apply(r.id)}>
                    <Plus size={13} /> 加入今天
                  </Button>
                  <button className="btn btn-ghost size-8 p-0 text-red-600" aria-label="删除食谱"
                          disabled={busy}
                          onClick={async () => { await api.deleteRecipe(uid, r.id); load() }}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              <ul className="mt-1 space-y-0.5">
                {r.items.map((it, i) => (
                  <li key={i} className="text-2xs text-muted">{itemLine(it)}</li>
                ))}
              </ul>
              <p className="mt-1 text-2xs text-faint">
                合计约 {fmtNutrient(r.items.reduce((n, it) => n + (it.intake?.energy_kcal || 0), 0))} kcal
              </p>
            </li>
          ))}
        </ul>
      )}
      {day && day.meals.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="text-xs font-semibold text-muted">把今天的某餐存为食谱</p>
          <div className="mt-2 flex gap-2">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="食谱名称" />
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {day.meals.map((m) => (
              <Button key={m.id} size="sm" variant="ghost" disabled={busy}
                      onClick={() => saveFromMeal(m.id)}>
                存「{m.items.map((i) => i.food_name).slice(0, 2).join('+')}
                {m.items.length > 2 ? '…' : ''}」
              </Button>
            ))}
          </div>
        </div>
      )}
    </Sheet>
  )
}
