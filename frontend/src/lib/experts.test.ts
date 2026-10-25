import { describe, expect, it } from 'vitest'
import {
  confidenceLabel, sourceRefText, statusLabel, relativeTime,
} from './experts'

describe('专家平台展示工具', () => {
  it('状态与置信度标签覆盖后端状态机', () => {
    expect(statusLabel('ready')).toBe('新分析')
    expect(statusLabel('invalidated')).toBe('已失效')
    expect(statusLabel('unknown-x')).toBe('unknown-x') // 未知状态原样展示不抛错
    expect(confidenceLabel('high')).toBe('数据充分')
    expect(confidenceLabel('low')).toBe('数据有限')
  })

  it('追溯链文本解析 checkin:ID:revision:N', () => {
    expect(sourceRefText('checkin:42:revision:0')).toBe('打卡 #42')
    expect(sourceRefText('checkin:42:revision:2')).toBe('打卡 #42（修订 2）')
    expect(sourceRefText('other:ref')).toBe('other:ref')
  })

  it('相对时间格式化', () => {
    expect(relativeTime(new Date().toISOString())).toBe('刚刚')
    expect(relativeTime(new Date(Date.now() - 5 * 60000).toISOString())).toBe('5 分钟前')
    expect(relativeTime(new Date(Date.now() - 3 * 3600000).toISOString())).toBe('3 小时前')
    expect(relativeTime(new Date(Date.now() - 2 * 86400000).toISOString())).toBe('2 天前')
    expect(relativeTime('not-a-date')).toBe('not-a-date')
  })
})
