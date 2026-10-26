import { describe, expect, it } from 'vitest'
import { normalizeSession, useApp } from './store'
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

  it('本次替换只改变当前会话，并保留原动作与计划位置', () => {
    useApp.setState({ uid: 'u', session: null })
    useApp.getState().startSession('周一 · 推', [{
      exercise_id: 'barbell_bench_press', name: '杠铃平板卧推',
      target: { sets: 3, reps: 10, weight: 60 }, planIndex: 0, logged: [],
    }], { planId: 7, planVersion: 3 })
    useApp.getState().replaceExercise(0, '哑铃卧推', 'dumbbell_bench_press')
    const entry = useApp.getState().session!.entries[0]
    expect(entry).toMatchObject({
      exercise_id: 'barbell_bench_press',
      replaced_from_id: 'barbell_bench_press',
      replace_exercise_id: 'dumbbell_bench_press',
      replaced_with: '哑铃卧推',
      planIndex: 0,
    })
    expect(useApp.getState().session).toMatchObject({ planId: 7, planVersion: 3 })
    useApp.setState({ session: null })
  })

  it('替换改变测量类型时同步更新输入口径并清空旧负重', () => {
    useApp.setState({ uid: 'u', session: null })
    useApp.getState().startSession('周一 · 拉', [{
      exercise_id: 'lat_pulldown', name: '高位下拉', measurement: 'weight_reps',
      target: { sets: 3, reps: 10, weight: 50 }, planIndex: 1, logged: [],
    }], { planId: 8, planVersion: 1 })
    useApp.getState().replaceExercise(0, '引体向上', 'pull_up', 'bodyweight_reps')
    const entry = useApp.getState().session!.entries[0]
    expect(entry.measurement).toBe('bodyweight_reps')
    expect(entry.target).toMatchObject({ sets: 3, reps: 10, weight: null })
    useApp.setState({ session: null })
  })

  it('旧暂停/结束会话保留旧状态', () => {
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
