import { describe, expect, it } from 'vitest'
import { fmtDelta, fmtNum, sourceRefText } from './body'

describe('身体数据展示工具', () => {
  it('未测量值显示 — 而不是 0', () => {
    expect(fmtNum(null, 'kg')).toBe('—')
    expect(fmtNum(0, 'kg')).toBe('0kg')
    expect(fmtNum(74.25, 'kg')).toBe('74.3kg')
  })

  it('变化值带符号', () => {
    expect(fmtDelta(-1.2, 'kg')).toBe('-1.2kg')
    expect(fmtDelta(0.5, 'cm')).toBe('+0.5cm')
    expect(fmtDelta(null)).toBe('—')
  })

  it('来源追溯链', () => {
    expect(sourceRefText('body:7:revision:0')).toBe('测量 #7')
    expect(sourceRefText('body:7:revision:2')).toBe('测量 #7（修订 2）')
  })
})
