import { useEffect, useMemo, useState } from 'react'
import { Plus } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, Select, Sheet, Spinner } from '../../components/Bits'
import { useApp } from '../../store'
import type { FoodItem, MealType } from '../../types'
import { MEAL_LABEL, NUTRIENT_META, fmtNutrient } from '../../lib/nutrition'

/** 添加食物：搜索/分类/自定义录入 → 选份量 → 加入指定餐次 */
export default function FoodPicker({ mealType, date, onClose, onSaved }:
  { mealType: MealType; date: string; onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const [scope, setScope] = useState<'all' | 'mine'>('all')
  const [foods, setFoods] = useState<FoodItem[]>([])
  const [categories, setCategories] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<FoodItem | null>(null)
  const [amount, setAmount] = useState('1')
  const [unit, setUnit] = useState('')
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const t = setTimeout(() => {
      api.foods(uid, { q, category, scope: scope === 'mine' ? 'mine' : undefined })
        .then((r) => { setFoods(r.foods); setCategories(r.categories) })
        .catch((e) => setError((e as ApiError).message))
    }, 200)
    return () => clearTimeout(t)
  }, [uid, q, category, scope])

  const preview = useMemo(() => {
    if (!selected) return null
    const grams = Number(amount) * (selected.serving_units.find(
      (u) => u.unit === (unit || selected.serving_units[0]?.unit))?.grams ?? 0)
    if (!grams) return null
    const factor = grams / selected.reference_amount
    return Object.fromEntries(NUTRIENT_META.map((m) => [m.key,
      selected[m.key as keyof FoodItem] as number | null == null ? null
        : Math.round(Number(selected[m.key as keyof FoodItem]) * factor * 10) / 10]))
  }, [selected, amount, unit])

  async function add() {
    if (!selected) return
    setBusy(true); setError('')
    try {
      await api.saveMeal(uid, {
        date, meal_type: mealType,
        items: [{ food_id: selected.id, amount: Number(amount),
                  unit: unit || selected.serving_units[0]?.unit || '克' }],
      })
      onSaved(); onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open title={`记录${MEAL_LABEL[mealType]} · 选食物`} onClose={onClose} wide>
      {creating ? (
        <CustomFoodForm onDone={(f) => { setCreating(false); setSelected(f) }}
                        onCancel={() => setCreating(false)} />
      ) : selected ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-[15px] font-semibold">{selected.name}</p>
              <p className="mt-0.5 text-2xs text-muted">
                每 {selected.reference_amount}{selected.reference_unit}：
                {NUTRIENT_META.slice(0, 4).map((m) =>
                  `${m.label} ${fmtNutrient(selected[m.key as keyof FoodItem] as number | null)}`).join(' · ')}
                <br />来源：{selected.source_name ?? '—'}
              </p>
            </div>
            <button className="btn btn-ghost text-xs" onClick={() => setSelected(null)}>重选</button>
          </div>
          <div className="flex items-end gap-2">
            <label className="flex-1">
              <span className="mb-1 block text-xs text-muted">份量</span>
              <Input value={amount} onChange={(e) => setAmount(e.target.value)}
                     inputMode="decimal" placeholder="数量" />
            </label>
            <label className="w-28">
              <span className="mb-1 block text-xs text-muted">单位</span>
              <Select value={unit || selected.serving_units[0]?.unit || ''}
                      onChange={(e) => setUnit(e.target.value)}>
                {selected.serving_units.map((u) => (
                  <option key={u.unit} value={u.unit}>{u.unit}（{u.grams}g）</option>
                ))}
              </Select>
            </label>
          </div>
          {preview && (
            <p className="rounded-xl bg-canvas p-2.5 text-xs leading-relaxed">
              本条：{NUTRIENT_META.slice(0, 4).map((m) =>
                `${m.label} ${fmtNutrient(preview[m.key], m.unit === 'kcal' ? '' : m.unit)}`
              ).join(' · ')}
            </p>
          )}
          {error && <ErrorBox message={error} />}
          <Button block disabled={busy || !Number(amount)} onClick={add}>
            <Plus size={16} /> {busy ? '保存中…' : `加入${MEAL_LABEL[mealType]}`}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2">
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索食物 / 别名 / 品牌" />
            <Select value={scope} onChange={(e) => setScope(e.target.value as 'all' | 'mine')}
                    className="w-24">
              <option value="all">全部</option>
              <option value="mine">我的</option>
            </Select>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button className={`tag ${!category ? 'bg-accent-soft text-accent-deep' : 'bg-ink/5 text-muted'}`}
                    onClick={() => setCategory('')}>全部分类</button>
            {Object.entries(categories).map(([key, label]) => (
              <button key={key}
                      className={`tag ${category === key ? 'bg-accent-soft text-accent-deep' : 'bg-ink/5 text-muted'}`}
                      onClick={() => setCategory(key)}>{label}</button>
            ))}
          </div>
          {error && <ErrorBox message={error} />}
          {!foods ? <Spinner /> : foods.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted">
              没有找到「{q}」——可以自己录入（营养标签抄包装即可）
            </p>
          ) : (
            <ul className="max-h-[50vh] divide-y divide-line overflow-y-auto">
              {foods.map((f) => (
                <li key={f.id}>
                  <button className="flex w-full items-center justify-between gap-2 py-2.5 text-left"
                          onClick={() => { setSelected(f); setUnit(''); setAmount(
                            f.serving_units[0] && f.serving_units[0].unit !== '克' ? '1' : '100') }}>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">
                        {f.name}
                        {f.verified_status === 'user_created'
                          && <span className="ml-1 text-2xs text-faint">（自录）</span>}
                      </span>
                      <span className="block text-2xs text-muted">
                        {categories[f.category] ?? f.category} ·
                        每 {f.reference_amount}{f.reference_unit} {fmtNutrient(f.energy_kcal)} kcal
                      </span>
                    </span>
                    <span className="shrink-0 text-2xs text-faint">{f.source_name}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button variant="ghost" block onClick={() => setCreating(true)}>
            <Plus size={15} /> 自定义食物（录入营养标签）
          </Button>
        </div>
      )}
    </Sheet>
  )
}

/** 自定义食物：营养标签按 reference_amount 口径，未知项留空 */
function CustomFoodForm({ onDone, onCancel }:
  { onDone: (f: FoodItem) => void; onCancel: () => void }) {
  const uid = useApp((s) => s.uid)
  const [form, setForm] = useState({
    name: '', category: 'other', reference_amount: '100', reference_unit: 'g',
    unitName: '份', unitGrams: '100',
    energy_kcal: '', protein_g: '', carbohydrate_g: '', fat_g: '', fiber_g: '', sodium_mg: '',
  })
  const [cats, setCats] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    api.foods(uid).then((r) => setCats(r.categories)).catch(() => {})
  }, [uid])

  async function submit() {
    setBusy(true); setError('')
    const num = (v: string) => (v.trim() === '' ? null : Number(v))
    try {
      const resp = await api.addFood(uid, {
        name: form.name, category: form.category,
        serving_units: [{ unit: '克', grams: 1 },
                        ...(form.unitName && Number(form.unitGrams) > 0
                          ? [{ unit: form.unitName, grams: Number(form.unitGrams) }] : [])],
        reference_amount: Number(form.reference_amount) || 100,
        reference_unit: form.reference_unit,
        energy_kcal: num(form.energy_kcal), protein_g: num(form.protein_g),
        carbohydrate_g: num(form.carbohydrate_g), fat_g: num(form.fat_g),
        fiber_g: num(form.fiber_g), sodium_mg: num(form.sodium_mg),
      })
      onDone(resp.food)
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold">自定义食物</p>
      <p className="text-2xs leading-relaxed text-muted">
        营养值按「每份参考量」填写（包装标签通常是每 100g 或每份）；不知道的项留空
        （保持未知，不会按 0 计算）。仅你自己可见。
      </p>
      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2"><span className="mb-1 block text-xs text-muted">名称 *</span>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                 placeholder="如：某品牌全麦贝果" /></label>
        <label><span className="mb-1 block text-xs text-muted">分类</span>
          <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {Object.entries(cats).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select></label>
        <div className="grid grid-cols-2 gap-2">
          <label><span className="mb-1 block text-xs text-muted">参考量</span>
            <Input value={form.reference_amount} inputMode="decimal"
                   onChange={(e) => setForm({ ...form, reference_amount: e.target.value })} /></label>
          <label><span className="mb-1 block text-xs text-muted">单位</span>
            <Select value={form.reference_unit}
                    onChange={(e) => setForm({ ...form, reference_unit: e.target.value })}>
              <option value="g">g</option><option value="毫升">毫升</option>
            </Select></label>
        </div>
        <label><span className="mb-1 block text-xs text-muted">常用单位名</span>
          <Input value={form.unitName} onChange={(e) => setForm({ ...form, unitName: e.target.value })}
                 placeholder="如：个" /></label>
        <label><span className="mb-1 block text-xs text-muted">该单位克数</span>
          <Input value={form.unitGrams} inputMode="decimal"
                 onChange={(e) => setForm({ ...form, unitGrams: e.target.value })} /></label>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[['energy_kcal', '能量 kcal'], ['protein_g', '蛋白 g'], ['carbohydrate_g', '碳水 g'],
          ['fat_g', '脂肪 g'], ['fiber_g', '纤维 g'], ['sodium_mg', '钠 mg']].map(
          ([key, label]) => (
            <label key={key}><span className="mb-1 block text-2xs text-muted">{label}</span>
              <Input value={form[key as keyof typeof form]} inputMode="decimal"
                     onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>
          ))}
      </div>
      {error && <ErrorBox message={error} />}
      <div className="flex gap-2">
        <Button disabled={busy || !form.name.trim()} onClick={submit}>
          {busy ? '保存中…' : '保存并选用'}
        </Button>
        <Button variant="ghost" onClick={onCancel}>返回</Button>
      </div>
    </div>
  )
}
