import { beforeEach, describe, expect, it, vi } from 'vitest'

// idb-keyval 用内存 Map 模拟（vitest node 环境没有 IndexedDB）
const store = new Map<string, unknown>()
vi.mock('idb-keyval', () => ({
  get: vi.fn(async (k: string) => store.get(k)),
  set: vi.fn(async (k: string, v: unknown) => { store.set(k, v) }),
  del: vi.fn(async (k: string) => { store.delete(k) }),
}))

import { discardFailed, enqueueCheckin, failedItems,
         queuedCount, queuedItems, retryFailed, syncQueue } from './offline'

// navigator.locks 在 node 测试环境不存在 → 自动退化为进程内 promise 链

describe('offline queue sync (M5.1 P0-1 并发安全)', () => {
  beforeEach(() => store.clear())

  it('syncs queued items in order with stable submission ids', async () => {
    await enqueueCheckin('u1', 'training', { n: 1 }, 'sid-1')
    await enqueueCheckin('u1', 'training', { n: 2 }, 'sid-2')
    const seen: string[] = []
    const r = await syncQueue(async (_u, _t, _d, sid) => { seen.push(sid) })
    expect(seen).toEqual(['sid-1', 'sid-2'])
    expect(r).toEqual({ synced: 2, failed: 0, remaining: 0 })
    expect(await queuedItems()).toEqual([])
  })

  it('workout completed DURING sync is not overwritten (审查场景 1)', async () => {
    await enqueueCheckin('u1', 'training', { n: 'A' }, 'sid-A')
    let releaseA!: () => void
    const gate = new Promise<void>((resolve) => { releaseA = resolve })
    const send = vi.fn(async (_u: string, _t: string, d: unknown, sid: string) => {
      if (sid === 'sid-A') await gate          // A 在途时用户完成了训练 B
      void d
    })
    const syncing = syncQueue(send)
    await new Promise((r) => setTimeout(r, 20)) // 确保同步已进入锁内
    const enq = enqueueCheckin('u1', 'training', { n: 'B' }, 'sid-B')  // 不等待(会排队等锁)
    releaseA()
    const r = await syncing
    await enq
    // 本轮同步只带走了 A；B 安全落队不被覆盖 —— 由下一轮同步带走
    expect(r.synced).toBe(1)
    expect(await queuedCount()).toBe(1)
    const r2 = await syncQueue(send)
    expect(r2.synced).toBe(1)
    expect(await queuedCount()).toBe(0)
  })

  it('two concurrent sync loops are serialized and lose nothing (审查场景 2)', async () => {
    for (const sid of ['s1', 's2', 's3', 's4']) {
      await enqueueCheckin('u1', 'training', { sid }, sid)
    }
    const sent: string[] = []
    const send = async (_u: string, _t: string, _d: unknown, sid: string) => {
      await new Promise((r) => setTimeout(r, 10))
      sent.push(sid)
    }
    const [r1, r2] = await Promise.all([syncQueue(send), syncQueue(send)])
    expect(sent).toHaveLength(4)                 // 每条恰好一次
    expect(new Set(sent).size).toBe(4)
    expect(r1.synced + r2.synced).toBe(4)
    expect(await queuedCount()).toBe(0)
  })

  it('network failure keeps remaining; permanent 4xx moves to failed queue intact', async () => {
    await enqueueCheckin('u1', 'training', { bad: true }, 'sid-bad')
    await enqueueCheckin('u1', 'training', { good: true }, 'sid-good')
    await enqueueCheckin('u1', 'training', { later: true }, 'sid-later')
    const r = await syncQueue(async (_u, _t, data, _sid) => {
      if ((data as { bad?: boolean }).bad) {
        throw Object.assign(new Error('operations 校验拒绝'), { status: 422 })
      }
      if ((data as { later?: boolean }).later) {
        throw new Error('网络不可用')
      }
    })
    expect(r.synced).toBe(1)
    expect(r.failed).toBe(1)
    expect(r.remaining).toBe(1)                  // 断网条保留
    const failed = await failedItems()
    expect(failed).toHaveLength(1)
    expect(failed[0].submission_id).toBe('sid-bad')
    expect(failed[0].error).toContain('校验拒绝')
    const items = await queuedItems()
    expect(items[0].submission_id).toBe('sid-later')
  })

  it('retryFailed re-queues failed items with same submission id', async () => {
    await enqueueCheckin('u1', 'training', { x: 1 }, 'sid-x')
    await syncQueue(async () => { throw Object.assign(new Error('拒'), { status: 400 }) })
    expect((await failedItems())).toHaveLength(1)
    const retried: string[] = []
    const r = await retryFailed(async (_u, _t, _d, sid) => { retried.push(sid) })
    expect(r.synced).toBe(1)
    expect(retried).toEqual(['sid-x'])
    expect(await failedItems()).toEqual([])
  })

  it('stale syncing items are reset and processed on next sync', async () => {
    await enqueueCheckin('u1', 'training', { n: 1 }, 'sid-1')
    // 模拟崩溃残留：直接改底层存储状态
    const items = await queuedItems()
    store.set('fc-offline-item-' + items[0].id, { ...items[0], status: 'syncing' })
    const r = await syncQueue(async () => { /* ok */ })
    expect(r.synced).toBe(1)
    expect(await queuedCount()).toBe(0)
  })

  it('discardFailed removes a single record', async () => {
    await enqueueCheckin('u1', 'training', { x: 1 }, 'sid-x')
    await syncQueue(async () => { throw Object.assign(new Error('拒'), { status: 400 }) })
    const [item] = await failedItems()
    await discardFailed(item.id)
    expect(await failedItems()).toEqual([])
  })
})
