// 离线记录与同步（2.0 §10.5 + M1.1 P0-2）：
// - 每次训练提交带稳定 submission_id，服务端按 (user, id) 幂等——
//   "响应丢失后重试"不会重复入库。
// - 网络类失败（status 0/5xx）按序留在待同步队列。
// - 校验类永久失败（4xx）进入**失败队列**（可查看/重试/丢弃/导出），
//   绝不静默删除用户完成的训练。
import { get, set } from 'idb-keyval'

const QUEUE_KEY = 'fc-offline-queue-v1'
const FAILED_KEY = 'fc-offline-failed-v1'

export interface QueuedCheckin {
  id: string
  submission_id: string
  uid: string
  type: string
  data: unknown
  at: string
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

export async function enqueueCheckin(uid: string, type: string, data: unknown,
                                     submissionId: string) {
  const queue = (await get<QueuedCheckin[]>(QUEUE_KEY)) || []
  queue.push({
    id: `q-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    submission_id: submissionId, uid, type, data, at: new Date().toISOString(),
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

async function readFailed(): Promise<FailedCheckin[]> {
  return (await get<FailedCheckin[]>(FAILED_KEY)) || []
}
async function writeFailed(items: FailedCheckin[]) {
  await set(FAILED_KEY, items)
}

export async function failedItems(): Promise<FailedCheckin[]> {
  return readFailed()
}

export async function discardFailed(id: string) {
  await writeFailed((await readFailed()).filter((f) => f.id !== id))
}

export async function exportFailedJSON(): Promise<string> {
  return JSON.stringify(await readFailed(), null, 2)
}

async function syncQueueInto(
  send: (uid: string, type: string, data: unknown, submissionId: string) => Promise<void>,
): Promise<SyncResult> {
  const queue = (await get<QueuedCheckin[]>(QUEUE_KEY)) || []
  const remaining: QueuedCheckin[] = []
  const failed: FailedCheckin[] = []
  let synced = 0
  for (let i = 0; i < queue.length; i++) {
    const item = queue[i]
    try {
      await send(item.uid, item.type, item.data, item.submission_id)
      synced += 1
    } catch (err) {
      const status = (err as { status?: number }).status ?? 0
      if (status >= 400 && status < 500) {
        failed.push({ ...item, error: (err as Error).message,
                      failed_at: new Date().toISOString() }) // 永久失败：留档可重试
      } else {
        remaining.push(...queue.slice(i)) // 网络不可用：本条及之后全部保留
        break
      }
    }
  }
  await set(QUEUE_KEY, remaining)
  if (failed.length) await writeFailed([...(await readFailed()), ...failed])
  return { synced, failed: failed.length, remaining: remaining.length }
}

export async function syncQueue(
  send: (uid: string, type: string, data: unknown, submissionId: string) => Promise<void>,
): Promise<SyncResult> {
  return syncQueueInto(send)
}

export async function retryFailed(
  send: (uid: string, type: string, data: unknown, submissionId: string) => Promise<void>,
): Promise<SyncResult> {
  // 失败记录放回队列头部按序重试（submission_id 不变 → 服务端幂等兜底）
  const failed = await readFailed()
  if (failed.length) {
    const asQueued: QueuedCheckin[] = failed.map(({ error, failed_at, ...rest }) => rest)
    await writeFailed([])
    await set(QUEUE_KEY, [...asQueued, ...((await get<QueuedCheckin[]>(QUEUE_KEY)) || [])])
  }
  return syncQueueInto(send)
}
