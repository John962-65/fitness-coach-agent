import { describe, expect, it } from 'vitest'
import { normalizeSession } from './store'
import type { WorkoutSession } from './store'
import { cardioElapsedSeconds } from './components/workout/CardioTimer'

describe('旧训练会话兼容', () => {
  it('无 status 的进行中有氧会话恢复为原开始时间，不重新开始', () => {
    const old = {
      id: 's-old', mode: 'free', day: 'free', date: '2026-10-26',
      entries: [{
        exercise_id: 'running', name: '跑步', activity: 'cardio',
        cardio: { startedAt: 1_000, pausedAt: null, pausedTotalMs: 0, endedAt: null },
        target: { sets: '—', reps: '—', weight: null }, logged: [],
      }],
      started_at: '2026-10-26T10:00:00', notes: '',
    } as unknown as WorkoutSession
    const restored = normalizeSession(old)!
    expect(restored.entries[0].cardio).toMatchObject({
      status: 'running', startedAt: 1_000,
    })
    expect(cardioElapsedSeconds(restored.entries[0].cardio!, 61_000)).toBe(60)
  })

  it('旧暂停/结束会话保留原状态', () => {
    const make = (cardio: Record<string, unknown>) => ({
      id: 's-old', mode: 'free', day: 'free', date: '2026-10-26',
      entries: [{ exercise_id: 'running', name: '跑步', activity: 'cardio',
        cardio, target: { sets: '—', reps: '—', weight: null }, logged: [] }],
      started_at: '2026-10-26T10:00:00', notes: '',
    }) as unknown as WorkoutSession
    expect(normalizeSession(make({
      startedAt: 1_000, pausedAt: 6_000, pausedTotalMs: 0, endedAt: null,
    }))!.entries[0].cardio!.status).toBe('paused')
    expect(normalizeSession(make({
      startedAt: 1_000, pausedAt: null, pausedTotalMs: 0, endedAt: 11_000,
    }))!.entries[0].cardio!.status).toBe('ended')
  })
})
