// M6.1.1：统一训练数据校验规则锁定
import { describe, expect, it } from 'vitest'
import {
  parseTrainingNumber, validateReps, validateRpe, validateSetValues, validateWeight,
} from './validate'

describe('validateWeight', () => {
  it('留空（自重）与常规重量通过', () => {
    expect(validateWeight(null)).toBeNull()
    expect(validateWeight(0.5)).toBeNull()
    expect(validateWeight(180)).toBeNull()
    expect(validateWeight(500)).toBeNull()
  })
  it('负数 / 零 / 超上限拒绝', () => {
    expect(validateWeight(-50)).toMatchObject({})
    expect(validateWeight(-50)).toContain('重量需在')
    expect(validateWeight(0)).toContain('重量需在')
    expect(validateWeight(501)).toContain('重量需在')
  })
})

describe('validateReps', () => {
  it('正式组必填且为整数', () => {
    expect(validateReps(null, false)).toContain('正式组请填写次数')
    expect(validateReps(8.5, false)).toBe('次数需为整数')
    expect(validateReps(10, false)).toBeNull()
  })
  it('热身组次数可选；范围 1-100', () => {
    expect(validateReps(null, true)).toBeNull()
    expect(validateReps(0, true)).toContain('次数需为')
    expect(validateReps(101, false)).toContain('次数需为')
  })
})

describe('validateRpe / validateSetValues', () => {
  it('RPE 1-10（含小数档），越界拒绝', () => {
    expect(validateRpe(null)).toBeNull()
    expect(validateRpe(7.5)).toBeNull()
    expect(validateRpe(15)).toContain('RPE 取值范围')
    expect(validateRpe(0.5)).toContain('RPE 取值范围')
  })
  it('合并校验返回第一条错误；全部通过返回 null', () => {
    expect(validateSetValues(-50, 8, 7, false)).toContain('重量需在')
    expect(validateSetValues(80, null, 7, false)).toContain('正式组请填写次数')
    expect(validateSetValues(80, 10, 7, false)).toBeNull()
    expect(validateSetValues(null, null, null, true)).toBeNull() // 热身全留空
  })
})

describe('parseTrainingNumber', () => {
  it('空串=null、数字=number、非法=undefined', () => {
    expect(parseTrainingNumber('')).toBeNull()
    expect(parseTrainingNumber(' 67.5 ')).toBe(67.5)
    expect(parseTrainingNumber('abc')).toBeUndefined()
  })
})
