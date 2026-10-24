import { beforeEach, describe, expect, it, vi } from 'vitest'

// idb-keyval 用内存 Map 模拟（vitest node 环境没有 IndexedDB）
const store = new Map<string, unknown>()
vi.mock('idb-keyval', () => ({
  get: vi.fn(async (k: string) => store.get(k)),
  set: vi.fn(async (k: string, v: unknown) => { store.set(k, v) }),
}))

import { discardFailed, enqueueCheckin, failedItems,
         retryFailed, syncQueue } from './offline'

describe('offline queue sync (M1.1 P0-2)', () => {
  beforeEach(() => store.clear())

  it('syncs queued items in order with stable submission ids', async () => {
    await enqueueCheckin('u1', 'training', { n: 1 }, 'sid-1')
    await enqueueCheckin('u1', 'training', { n: 2 }, 'sid-2')
    const seen: string[] = []
    const r = await syncQueue(async (_u, _t, _d, sid) => { seen.push(sid) })
    expect(seen).toEqual(['sid-1', 'sid-2'])
    expect(r).toEqual({ synced: 2, failed: 0, remaining: 0 })
  })

  it('keeps the rest of the queue when network fails mid-way', async () => {
    await enqueueCheckin('u1', 'training', { n: 1 }, 'sid-1')
    await enqueueCheckin('u1', 'training', { n: 2 }, 'sid-2')
    await enqueueCheckin('u1', 'training', { n: 3 }, 'sid-3')
    let calls = 0
    const r = await syncQueue(async () => {
      calls += 1
      if (calls === 2) throw new Error('网络不可用') // status 0 → 网络类
    })
    expect(r.synced).toBe(1)
    expect(r.remaining).toBe(2)                      // 断网条及之后全部保留
    expect(await failedItems()).toEqual([])          // 网络失败不进失败队列
  })

  it('moves permanently rejected items (4xx) to a recoverable failed queue, never deletes them', async () => {
    await enqueueCheckin('u1', 'training', { bad: true }, 'sid-bad')
    await enqueueCheckin('u1', 'training', { good: true }, 'sid-good')
    const r = await syncQueue(async (_u, _t, data, _sid) => {
      if ((data as { bad?: boolean }).bad) {
        throw Object.assign(new Error('operations 必须是非空操作列表'), { status: 422 })
      }
    })
    expect(r.synced).toBe(1)
    expect(r.failed).toBe(1)
    const failed = await failedItems()
    expect(failed).toHaveLength(1)
    expect(failed[0].submission_id).toBe('sid-bad')
    expect(failed[0].error).toContain('操作列表') // 失败原因文本留档
  })

  it('retryFailed re-queues failed items with the same submission id (server idempotency dedupes)', async () => {
    await enqueueCheckin('u1', 'training', { bad: true }, 'sid-bad')
    await syncQueue(async () => {
      throw Object.assign(new Error('校验拒绝'), { status: 422 })
    })
    expect((await failedItems())).toHaveLength(1)
    const retriedSids: string[] = []
    const r = await retryFailed(async (_u, _t, _d, sid) => { retriedSids.push(sid) })
    expect(r.synced).toBe(1)
    expect(retriedSids).toEqual(['sid-bad'])         // 同一 submission_id 重试
    expect(await failedItems()).toEqual([])
  })

  it('discardFailed removes a single record from the failed queue', async () => {
    await enqueueCheckin('u1', 'training', { x: 1 }, 'sid-x')
    await syncQueue(async () => {
      throw Object.assign(new Error('拒绝'), { status: 400 })
    })
    const [item] = await failedItems()
    await discardFailed(item.id)
    expect(await failedItems()).toEqual([])
  })
})
