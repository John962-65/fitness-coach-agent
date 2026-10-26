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

describe('P5-C2：仅本次采用候选目标（applySessionTarget）', () => {
  const begin = (entries: Partial<Parameters<ReturnType<
    typeof useApp.getState>['addFreeExercise']>[0]>[] = []) => {
    useApp.setState({ uid: 'u', session: null })
    useApp.getState().startFreeSession()
    for (const e of entries) {
      useApp.getState().addFreeExercise({
        exercise_id: 'barbell_bench_press', name: '杠铃卧推',
        measurement: 'weight_reps',
        target: { sets: 3, reps: '8-12', weight: 60 }, logged: [],
        ...e,
      } as Parameters<ReturnType<typeof useApp.getState>['addFreeExercise']>[0])
    }
  }
  const entryAt = (i: number) => useApp.getState().session!.entries[i]

  it('仅本次采用：目标改变、已记录组与组法/超组/计时器原样保留', () => {
    begin([{}])
    useApp.getState().logSet(0, { type: 'weight_reps', weight_kg: 60,
      reps: 10, warmup: false } as never)
    useApp.getState().setEntryGroup(0, 'A')
    useApp.getState().setSupersetConfig('A', { rounds: 4 })
    useApp.getState().setEntryDraft(0, { reps: '10' })
    useApp.getState().startRest()

    const restBefore = useApp.getState().restEndsAt
    const outcome = useApp.getState().applySessionTarget(
      0, { sets: 3, reps: '8-12', weight_kg: 62.5 }, 'consider-increase-load')
    expect(outcome.applied).toBe(true)
    const entry = entryAt(0)
    expect(entry.target).toMatchObject({ sets: 3, weight: 62.5 })
    expect(entry.logged).toHaveLength(1)
    expect(entry.logged[0]).toMatchObject({ weight_kg: 60, reps: 10 })
    expect(entry.supersetGroup).toBe('A')
    expect(useApp.getState().session!.supersetConfig?.A?.rounds).toBe(4)
    expect(useApp.getState().session!.drafts?.[0]?.reps).toBe('10')
    expect(useApp.getState().restEndsAt).toBe(restBefore)
    expect(useApp.getState().session!.appliedTargets?.[0]).toMatchObject(
      { optionId: 'consider-increase-load' })
    // 仅本次：不触碰计划溯源
    expect(useApp.getState().session!.mode).toBe('free')
  })

  it('撤销本次调整后目标恢复原值', () => {
    begin([{}])
    useApp.getState().applySessionTarget(
      0, { weight_kg: 65 }, 'consider-increase-load')
    expect(entryAt(0).target.weight).toBe(65)
    expect(useApp.getState().revertSessionTarget(0)).toBe(true)
    expect(entryAt(0).target).toMatchObject({ sets: 3, reps: '8-12', weight: 60 })
    expect(useApp.getState().session!.appliedTargets?.[0]).toBeUndefined()
    expect(useApp.getState().revertSessionTarget(0)).toBe(false)
  })

  it('复杂组结构不接受普通负重覆盖（只展示方向）', () => {
    begin([{}])
    useApp.getState().setEntryDraft(0, { method: 'drop_set' })
    const outcome = useApp.getState().applySessionTarget(
      0, { weight_kg: 62.5, reps: '8-12' }, 'consider-increase-load')
    expect(outcome.applied).toBe(false)
    expect(outcome.incompatible).toContain('weight_kg')
    expect(entryAt(0).target.weight).toBe(60)
  })

  it('有氧/HIIT 与时长/距离记录不接受次数/负重字段', () => {
    begin([{ exercise_id: 'running', name: '跑步', activity: 'cardio',
             measurement: 'distance_time' }])
    const outcome = useApp.getState().applySessionTarget(
      0, { sets: 1, reps: 10, weight_kg: 20 }, 'keep-current')
    expect(outcome.applied).toBe(false)
    expect(outcome.incompatible).toEqual(['sets', 'reps', 'weight_kg'])
  })

  it('辅助动作采用降低辅助；刷新恢复（持久化会话含 appliedTargets）', () => {
    begin([{ exercise_id: 'assisted_dip', name: '辅助臂屈伸',
             measurement: 'assisted_reps' }])
    const outcome = useApp.getState().applySessionTarget(
      0, { sets: 3, reps: '8-12', assistance_kg: 17.5 },
      'consider-increase-load')
    expect(outcome.applied).toBe(true)
    expect(entryAt(0).target.weight).toBe(17.5)
    const persisted = useApp.getState().session!
    expect(persisted.appliedTargets?.[0]?.from.weight).toBe(60)
    // 模拟刷新：恢复持久化会话后撤销仍然有效
    useApp.setState({ uid: 'u', session: normalizeSession(persisted) })
    expect(useApp.getState().session!.appliedTargets?.[0]?.optionId)
      .toBe('consider-increase-load')
    useApp.getState().revertSessionTarget(0)
    expect(entryAt(0).target.weight).toBe(60)
  })

  it('移除动作时 appliedTargets 索引同步平移', () => {
    begin([{}, {}])
    useApp.getState().applySessionTarget(1, { weight_kg: 65 }, 'opt')
    useApp.getState().removeEntry(0)
    expect(useApp.getState().session!.appliedTargets?.[0]?.optionId).toBe('opt')
    expect(useApp.getState().session!.appliedTargets?.[1]).toBeUndefined()
  })
})
