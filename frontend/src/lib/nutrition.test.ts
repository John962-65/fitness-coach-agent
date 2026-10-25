import { describe, expect, it } from 'vitest'
import { fmtAmount, fmtNutrient, itemLine, shiftDate, targetPct } from './nutrition'

describe('营养展示工具', () => {
  it('未知营养素显示为 —，绝不显示成 0', () => {
    expect(fmtNutrient(null)).toBe('—')
    expect(fmtNutrient(undefined, 'g')).toBe('—')
    expect(fmtNutrient(0, 'g')).toBe('0g')
    expect(fmtNutrient(30.25, 'g')).toBe('30.3g')
  })

  it('目标比例：无目标或未知值为 null', () => {
    expect(targetPct(500, null)).toBeNull()
    expect(targetPct(null, 2000)).toBeNull()
    expect(targetPct(1000, 2000)).toBe(50)
  })

  it('条目行摘要区分未知能量', () => {
    expect(itemLine({ food_name: '米饭', amount: 1.5, unit: '碗',
                      intake: { energy_kcal: 348 } })).toBe('米饭 1.5碗 · 348 kcal')
    expect(itemLine({ food_name: '汤', amount: 1, unit: '碗',
                      intake: { energy_kcal: null } })).toBe('汤 1碗 · 能量未知')
  })

  it('日期平移与份量格式', () => {
    expect(shiftDate('2026-10-25', -1)).toBe('2026-10-24')
    expect(shiftDate('2026-10-31', 1)).toBe('2026-11-01')
    expect(fmtAmount(2)).toBe('2')
    expect(fmtAmount(1.5)).toBe('1.5')
  })
})
