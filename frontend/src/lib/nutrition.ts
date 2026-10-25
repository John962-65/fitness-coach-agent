// 营养展示工具（与后端口径一致：未知营养素不是 0）
import type { MealType } from '../types'

export const MEAL_LABEL: Record<MealType, string> = {
  breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐',
}
export const MEAL_ORDER: MealType[] = ['breakfast', 'lunch', 'dinner', 'snack']

/** 营养值展示：null → '—'（未知），绝不显示成 0 */
export function fmtNutrient(v: number | null | undefined, unit = ''): string {
  if (v === null || v === undefined) return '—'
  const n = Number.isInteger(v) ? String(v) : v.toFixed(1)
  return `${n}${unit}`
}

/** 目标达成比例（无目标/未知值返回 null，不显示假进度） */
export function targetPct(value: number | null | undefined,
                          target: number | null | undefined): number | null {
  if (value == null || !target) return null
  return Math.round((value / target) * 100)
}

export const NUTRIENT_META: { key: string; label: string; unit: string }[] = [
  { key: 'energy_kcal', label: '能量', unit: 'kcal' },
  { key: 'protein_g', label: '蛋白质', unit: 'g' },
  { key: 'carbohydrate_g', label: '碳水', unit: 'g' },
  { key: 'fat_g', label: '脂肪', unit: 'g' },
  { key: 'fiber_g', label: '膳食纤维', unit: 'g' },
  { key: 'sodium_mg', label: '钠', unit: 'mg' },
]

export function shiftDate(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function todayISO(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 每条目行摘要：名称 份量单位 · 能量（未知则 '—'） */
export function itemLine(item: {
  food_name: string; amount: number; unit: string
  intake: Record<string, number | null>
}): string {
  const kcal = item.intake?.energy_kcal
  return `${item.food_name} ${fmtAmount(item.amount)}${item.unit}` +
    (kcal != null ? ` · ${Math.round(kcal)} kcal` : ' · 能量未知')
}

export function fmtAmount(n: number): string {
  return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(2)))
}
