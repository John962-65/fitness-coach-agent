import { useEffect, useState } from 'react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, PageHeader, Select, Spinner } from '../../components/Bits'
import { useApp } from '../../store'
import type { NutritionReference, NutritionTargets } from '../../types'

/** 营养目标：你手动设置；参考估算只提供依据（Mifflin-St Jeor），不代你决定 */
export default function NutritionTargets() {
  const uid = useApp((s) => s.uid)
  const [targets, setTargets] = useState<NutritionTargets | null>(null)
  const [reference, setReference] = useState<NutritionReference | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.nutritionTargets(uid).then((r) => { setTargets(r.targets); setReference(r.reference) })
      .catch((e) => setError((e as ApiError).message))
  }, [uid])

  if (error && !targets) return <div className="pt-4"><ErrorBox message={error} /></div>
  if (!targets) return <Spinner />

  const current: NutritionTargets = targets
  const num = (v: string) => (v.trim() === '' ? null : Number(v))
  const set = (patch: Partial<NutritionTargets>) => {
    setTargets({ ...current, ...patch }); setSaved(false)
  }

  async function save() {
    setBusy(true); setError('')
    try {
      const r = await api.saveNutritionTargets(uid, { ...current,
        preferences: current.preferences ?? {}, allergies: current.allergies ?? [] })
      setTargets(r.targets); setSaved(true)
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <PageHeader title="营养目标" sub="目标由你设置；系统只提供有依据的参考估算" />
      <div className="card space-y-3">
        <div className="grid grid-cols-2 gap-3">
          {[['energy_kcal', '每日能量 kcal'], ['protein_g', '蛋白质 g'],
            ['carbohydrate_g', '碳水 g'], ['fat_g', '脂肪 g']].map(([key, label]) => (
            <label key={key}>
              <span className="mb-1 block text-xs text-muted">{label}（留空=不设）</span>
              <Input inputMode="decimal"
                     value={targets[key as keyof NutritionTargets] as number | null ?? ''}
                     onChange={(e) => set({ [key]: num(e.target.value) } as Partial<NutritionTargets>)} />
            </label>
          ))}
        </div>
        <label className="block">
          <span className="mb-1 block text-xs text-muted">记录意愿（影响建议方式）</span>
          <Select value={targets.precision_willing ?? ''}
                  onChange={(e) => set({ precision_willing: e.target.value || null })}>
            <option value="">未选择</option>
            <option value="willing_precise">愿意较精确记录</option>
            <option value="rough">粗略记录即可</option>
            <option value="minimal">只想记个大概</option>
          </Select>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-muted">过敏与食物限制（逗号分隔）</span>
          <Input value={(targets.allergies ?? []).join('，')}
                 onChange={(e) => set({ allergies: e.target.value.split(/[，,]/).map((s) => s.trim()).filter(Boolean) })} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-muted">预算 / 食材偏好备注</span>
          <Input value={targets.budget_note ?? ''}
                 onChange={(e) => set({ budget_note: e.target.value || null })} />
        </label>
        {error && <ErrorBox message={error} />}
        {saved && <p className="text-xs text-emerald-700">已保存。目标变化后当天分析会自动更新。</p>}
        <Button disabled={busy} onClick={save}>{busy ? '保存中…' : '保存目标'}</Button>
      </div>

      {reference && (
        <div className="card mt-4">
          <p className="text-sm font-semibold">参考估算（Mifflin-St Jeor 公式）</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">{reference.note}</p>
          {reference.bmr ? (
            <div className="mt-2 space-y-1 text-[13px]">
              <p>基础代谢（BMR）≈ <b className="nums">{reference.bmr}</b> kcal/天</p>
              {Object.entries(reference.activity_factors ?? {}).map(([k, v]) => (
                <p key={k} className="text-muted">
                  {v.label}：维持能量约 <b className="nums text-ink">{v.tdee}</b> kcal
                </p>
              ))}
              {reference.protein_reference && (
                <p className="text-muted">
                  蛋白质常用参考区间：{
                    reference.protein_reference.per_kg_range[0]}-{reference.protein_reference.per_kg_range[1]}
                  g/kg 体重（{reference.protein_reference.at_weight_kg}kg 约{' '}
                  {Math.round(reference.protein_reference.per_kg_range[0] * reference.protein_reference.at_weight_kg)}-
                  {Math.round(reference.protein_reference.per_kg_range[1] * reference.protein_reference.at_weight_kg)}g）
                </p>
              )}
            </div>
          ) : (
            <p className="mt-2 text-xs text-muted">{reference.energy_kcal === null && '档案信息不足，无法估算'}</p>
          )}
          <p className="mt-2 text-2xs leading-relaxed text-faint">
            估算值仅供参考（个体差异 ±10% 以上）；最终目标数值由你决定并可随时调整。
          </p>
        </div>
      )}
    </div>
  )
}
