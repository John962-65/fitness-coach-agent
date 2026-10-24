import { beforeEach, describe, expect, it, vi } from 'vitest'

// idb-keyval 用内存 Map 模拟（vitest node 环境没有 IndexedDB）
const store = new Map<string, unknown>()
vi.mock('idb-keyval', () => ({
  get: vi.fn(async (k: string) => store.get(k)),
  set: vi.fn(async (k: string, v: unknown) => { store.set(k, v) }),
}))

import { enqueueCheckin, syncQueue } from './offline'

describe('offline queue sync', () => {
  beforeEach(() => store.clear())

  it('syncs queued items in order and clears the queue', async () => {
    await enqueueCheckin('u1', 'training', { exercises: [{ name: '卧推' }] })
    await enqueueCheckin('u1', 'training', { exercises: [{ name: '深蹲' }] })
    const sent: string[] = []
    const r = await syncQueue(async (_uid, _type, data) => {
      sent.push((data as { exercises: { name: string }[] }).exercises[0].name)
    })
    expect(sent).toEqual(['卧推', '深蹲'])
    expect(r).toEqual({ synced: 2, dropped: 0, remaining: 0 })
  })

  it('keeps the rest of the queue when network fails mid-way', async () => {
    await enqueueCheckin('u1', 'training', { n: 1 })
    await enqueueCheckin('u1', 'training', { n: 2 })
    await enqueueCheckin('u1', 'training', { n: 3 })
    let calls = 0
    const r = await syncQueue(async () => {
      calls += 1
      if (calls === 2) throw new Error('网络不可用') // status 0 → 网络类
    })
    expect(r.synced).toBe(1)
    expect(r.remaining).toBe(2)
  })

  it('drops permanently rejected items (4xx) without blocking', async () => {
    await enqueueCheckin('u1', 'training', { bad: true })
    await enqueueCheckin('u1', 'training', { good: true })
    const r = await syncQueue(async (_uid, _type, data) => {
      if ((data as { bad?: boolean }).bad) {
        throw Object.assign(new Error('校验拒绝'), { status: 422 })
      }
    })
    expect(r.synced).toBe(1)
    expect(r.dropped).toBe(1)
    expect(r.remaining).toBe(0)
  })
})
