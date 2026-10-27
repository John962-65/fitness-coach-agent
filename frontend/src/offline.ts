// 离线记录与同步（2.0 §10.5 + M1.1 P0-2 + M5.1 P0-1）。
//
// M5.1 重写要点（外部审查指出的并发丢失）：
// - 按 ID 独立存储（每条一个 key），不再整表读写覆盖；
// - 全局异步互斥锁：入队/同步/失败转移全部串行——同步进行中完成的训练
//   不会丢，两个同步循环也不会交错；
// - 状态迁移 pending→syncing→(删除 | failed)；崩溃残留的 syncing 在下次
//   同步开始时重置回 pending；
// - 4xx 永久失败先写失败库、后删原记录（目标写入成功前绝不删除）；
// - 服务端 submission_id 幂等不变（重复投递不重复入库）。
import { del, get, keys, set } from 'idb-keyval'

const QUEUE_KEY = 'fc-offline-queue-v1'        // string[]：待同步 ID 顺序表
const FAILED_KEY = 'fc-offline-failed-v1'      // FailedCheckin[]
const ITEM_PREFIX = 'fc-offline-item-'         // 每条记录独立 key
const LOCK_KEY = 'fc-offline-lock-v1'          // 跨标签页互斥（尽力而为）

export interface QueuedCheckin {
  id: string
  submission_id: string
  uid: string
  type: string
  data: unknown
  at: string
  status?: 'pending' | 'syncing'
}

export interface FailedCheckin extends QueuedCheckin {
  error: string
  failed_at: string
}

export interface SyncResult {
  synced: number
  failed: number
  remaining: number
}

export function newSubmissionId(): string {
  return `sub-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

// ---- 全局异步互斥：同进程 promise 链 + 跨标签页 navigator.locks（可用时）----

let chain: Promise<unknown> = Promise.resolve()

function withLock<T>(fn: () => Promise<T>): Promise<T> {
  const run = chain.then(fn, fn)
  chain = run.catch(() => { /* 锁链条不断 */ })
  return run
}

async function withTabLock<T>(name: string, fn: () => Promise<T>): Promise<T> {
  // Node ≤20（vitest 环境）没有全局 navigator；浏览器用 Web Locks 跨标签页互斥
  const locks = typeof navigator === 'undefined'
    ? undefined
    : (navigator as Navigator & { locks?: { request: (n: string, cb: () => Promise<T>) => Promise<T> } }).locks
  if (!locks) return withLock(fn)
  return locks.request(name, () => withLock(fn))
}

// ---- 队列操作（全部在锁内）----

async function readIndex(): Promise<string[]> {
  return (await get<string[]>(QUEUE_KEY)) || []
}
async function writeIndex(ids: string[]): Promise<void> {
  await set(QUEUE_KEY, ids)
}

export async function enqueueCheckin(uid: string, type: string, data: unknown,
                                     submissionId: string): Promise<number> {
  const item: QueuedCheckin = {
    id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    submission_id: submissionId, uid, type, data,
    at: new Date().toISOString(), status: 'pending',
  }
  return withTabLock(LOCK_KEY, async () => {
    await set(ITEM_PREFIX + item.id, item)
    await writeIndex([...(await readIndex()), item.id])   // 追加，不整表覆盖
    return (await readIndex()).length
  })
}

export async function queuedCount(): Promise<number> {
  return (await readIndex()).length
}

export async function queuedItems(): Promise<QueuedCheckin[]> {
  const ids = await readIndex()
  const items: QueuedCheckin[] = []
  for (const id of ids) {
    const item = await get<QueuedCheckin>(ITEM_PREFIX + id)
    if (item) items.push(item)
  }
  return items
}

async function readFailed(): Promise<FailedCheckin[]> {
  return (await get<FailedCheckin[]>(FAILED_KEY)) || []
}
async function writeFailed(items: FailedCheckin[]): Promise<void> {
  await set(FAILED_KEY, items)
}

export async function failedItems(): Promise<FailedCheckin[]> {
  return readFailed()
}

export async function discardFailed(id: string): Promise<void> {
  await withTabLock(LOCK_KEY, async () => {
    await writeFailed((await readFailed()).filter((f) => f.id !== id))
  })
}

export async function exportFailedJSON(): Promise<string> {
  return JSON.stringify(await readFailed(), null, 2)
}

type Send = (uid: string, type: string, data: unknown, submissionId: string) => Promise<void>

async function syncLocked(send: Send): Promise<SyncResult> {
  // 崩溃残留的 syncing 复位；然后按序投递 pending
  const ids = await readIndex()
  const reset: string[] = []
  for (const id of ids) {
    const item = await get<QueuedCheckin>(ITEM_PREFIX + id)
    if (!item) { reset.push(id); continue }             // 记录丢失 → 清索引
    if (item.status === 'syncing') {
      await set(ITEM_PREFIX + id, { ...item, status: 'pending' })
    }
  }
  if (reset.length) await writeIndex(ids.filter((id) => !reset.includes(id)))

  let synced = 0
  let failed = 0
  for (;;) {
    // 每轮在锁内重新取下一条 pending（同步期间新入队的也能被本轮带走）
    const currentIds = await readIndex()
    let picked: string | undefined
    for (const id of currentIds) {
      const it = await get<QueuedCheckin>(ITEM_PREFIX + id)
      if (it && (it.status || 'pending') === 'pending') { picked = id; break }
    }
    if (!picked) break
    const item = await get<QueuedCheckin>(ITEM_PREFIX + picked)
    if (!item) {
      await writeIndex(currentIds.filter((i) => i !== picked))
      continue
    }
    await set(ITEM_PREFIX + item.id, { ...item, status: 'syncing' })
    try {
      await send(item.uid, item.type, item.data, item.submission_id)
      // 成功：先删记录再删索引（顺序保证可重入安全）
      await del(ITEM_PREFIX + item.id)
      const rest = (await readIndex()).filter((id) => id !== item.id)
      await writeIndex(rest)
      synced += 1
    } catch (err) {
      const status = (err as { status?: number }).status ?? 0
      if (status >= 400 && status < 500) {
        // 永久失败：先写失败库（成功后才删原记录）
        await writeFailed([...(await readFailed()), {
          ...item, status: 'pending', error: (err as Error).message,
          failed_at: new Date().toISOString(),
        }])
        await del(ITEM_PREFIX + item.id)
        await writeIndex((await readIndex()).filter((id) => id !== item.id))
        failed += 1
      } else {
        // 网络类：留在队列（本条及之后都保留），复位状态
        await set(ITEM_PREFIX + item.id, { ...item, status: 'pending' })
        break
      }
    }
  }
  return { synced, failed, remaining: (await readIndex()).length }
}

export async function syncQueue(send: Send): Promise<SyncResult> {
  return withTabLock(LOCK_KEY, () => syncLocked(send))
}

export async function retryFailed(send: Send): Promise<SyncResult> {
  return withTabLock(LOCK_KEY, async () => {
    const failedList = await readFailed()
    if (failedList.length) {
      // 失败记录按原 submission_id 放回队首（服务端幂等兜底）
      for (const { error, failed_at, ...rest } of failedList) {
        void error; void failed_at
        const item = { ...rest, status: 'pending' as const }
        await set(ITEM_PREFIX + item.id, item)
      }
      const ids = failedList.map((f) => f.id)
      const index = await readIndex()
      await writeIndex([...ids.filter((id) => !index.includes(id)), ...index])
      await writeFailed([])
    }
    return syncLocked(send)
  })
}


/** 账户删除后清空可归属本机的离线数据（队列、失败记录、锁）。 */
export async function clearOfflineData(): Promise<void> {
  await withTabLock(LOCK_KEY, async () => {
    try {
      const all = await keys()
      for (const key of all) {
        const name = String(key)
        if (name.startsWith('fc-offline-')) await del(key)
      }
    } catch {
      // IndexedDB 不可用时不阻塞账户删除
    }
  })
}
