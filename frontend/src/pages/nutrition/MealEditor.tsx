import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, Select, Sheet } from '../../components/Bits'
import { useApp } from '../../store'
import type { DayNutrition, MealType, ServingUnit } from '../../types'
import { MEAL_LABEL, fmtNutrient, itemLine } from '../../lib/nutrition'

type MealRow = DayNutrition['meals'][number]

/** 编辑餐次：改份量/单位/备注、换餐次、删除整餐（服务端按快照重算） */
export default function MealEditor({ meal, date, onClose }:
  { meal: MealRow; date: string; onClose: () => void }) {
  const uid = useApp((s) => s.uid)
  const [items, setItems] = useState<MealRow['items']>(meal.items)
  const [notes, setNotes] = useState(meal.notes || '')
  const [mealType, setMealType] = useState<MealType>(meal.meal_type)
  const [units, setUnits] = useState<Record<string, ServingUnit[]>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    for (const item of meal.items) {
      if (units[item.food_id]) continue
      api.foodDetail(item.food_id, uid)
        .then((f) => setUnits((u) => ({ ...u, [item.food_id]: f.serving_units })))
        .catch(() => setUnits((u) => ({ ...u, [item.food_id]: [{ unit: item.unit, grams: item.grams / (item.amount || 1) }] })))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meal.id, uid])

  async function save() {
    setBusy(true); setError('')
    try {
      await api.updateMeal(uid, meal.id, {
        items: items.map((it) => ({ food_id: it.food_id, amount: it.amount, unit: it.unit })),
        notes, meal_type: mealType,
      })
      onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  async function remove() {
    setBusy(true); setError('')
    try {
      await api.deleteMeal(uid, meal.id)
      onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open title={`编辑${MEAL_LABEL[meal.meal_type]} · ${date}`} onClose={onClose}>
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="rounded-xl border border-line p-2.5">
            <p className="text-[13px] font-medium">{item.food_name}</p>
            <div className="mt-1.5 flex items-center gap-2">
              <Input className="w-24" inputMode="decimal" value={String(item.amount)}
                     onChange={(e) => setItems(items.map((it, j) =>
                       j === i ? { ...it, amount: Number(e.target.value) || 0 } : it))} />
              <Select className="w-40" value={item.unit}
                      onChange={(e) => setItems(items.map((it, j) =>
                        j === i ? { ...it, unit: e.target.value } : it))}>
                {(units[item.food_id] ?? [{ unit: item.unit, grams: 0 }]).map((u) => (
                  <option key={u.unit} value={u.unit}>{u.unit}（{u.grams}g）</option>
                ))}
              </Select>
            </div>
            <p className="mt-1 text-2xs text-muted">{itemLine(items[i])}</p>
          </li>
        ))}
      </ul>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <label><span className="mb-1 block text-xs text-muted">所属餐次</span>
          <Select value={mealType} onChange={(e) => setMealType(e.target.value as MealType)}>
            {Object.entries(MEAL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select></label>
        <label><span className="mb-1 block text-xs text-muted">备注</span>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      </div>
      <p className="mt-2 text-2xs leading-relaxed text-muted">
        保存后统计按记录时的营养快照重算（未知营养素保持未知，不按 0 计）。克数参考：
        {items.map((it) => `${it.food_name}≈${fmtNutrient(it.grams, 'g')}`).join('、')}。
      </p>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <div className="mt-3 flex gap-2">
        <Button disabled={busy} onClick={save}>{busy ? '保存中…' : '保存修改'}</Button>
        <Button variant="ghost" className="!text-red-600" disabled={busy} onClick={remove}>
          <Trash2 size={15} /> 删除这餐
        </Button>
      </div>
    </Sheet>
  )
}
