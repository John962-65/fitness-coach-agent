// 离线记录与同步（2.0 §10.5）：IndexedDB 队列，恢复联网后同步。
// 永久性错误（4xx：校验拒绝）不重试、留痕丢弃；网络错误保留待下轮。
import { get, set } from 'idb-keyval'

const QUEUE_KEY = 'fc-offline-queue-v1'

export interface QueuedCheckin {
  id: string
  uid: string
  type: string
  data: unknown
  at: string
}

export interface SyncResult {
  synced: number
  dropped: number
  remaining: number
}

export async function enqueueCheckin(uid: string, type: string, data: unknown) {
  const queue = (await get<QueuedCheckin[]>(QUEUE_KEY)) || []
  queue.push({
    id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    uid, type, data, at: new Date().toISOString(),
  })
  await set(QUEUE_KEY, queue)
  return queue.length
}

export async function queuedCount(): Promise<number> {
  return ((await get<QueuedCheckin[]>(QUEUE_KEY)) || []).length
}

export async function queuedItems(): Promise<QueuedCheckin[]> {
  return (await get<QueuedCheckin[]>(QUEUE_KEY)) || []
}

export async function syncQueue(
  send: (uid: string, type: string, data: unknown) => Promise<void>,
): Promise<SyncResult> {
  const queue = (await get<QueuedCheckin[]>(QUEUE_KEY)) || []
  const remaining: QueuedCheckin[] = []
  let synced = 0
  let dropped = 0
  for (let i = 0; i < queue.length; i++) {
    const item = queue[i]
    try {
      await send(item.uid, item.type, item.data)
      synced += 1
    } catch (err) {
      const status = (err as { status?: number }).status ?? 0
      if (status >= 400 && status < 500) {
        dropped += 1 // 校验类永久失败：重试无意义，留痕丢弃
      } else {
        remaining.push(...queue.slice(i)) // 网络不可用：本条及之后全部保留
        break // 按序同步：一旦断网，后面不再尝试
      }
    }
  }
  await set(QUEUE_KEY, remaining)
  return { synced, dropped, remaining: remaining.length }
}
