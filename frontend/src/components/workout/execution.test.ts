import { describe, expect, it } from 'vitest'
import {
  cardioElapsedSeconds, createCardioState, endCardio, pauseCardio, resumeCardio,
} from './CardioTimer'
import {
  completeHiitPhase, createHiitRun, hiitPhaseElapsed, needsHiitConfirmation,
  pauseHiit, resumeHiit, skipHiitPhase, stopHiitEarly,
} from './HiitRunner'
import type { HiitPlan } from '../../types'

const plan = (rounds = 2): HiitPlan => ({
  name: '测试间歇',
  blocks: [{ name: '开合跳', exercise_id: 'jumping_jack',
    work_seconds: 30, rest_seconds: 20, rounds }],
})

describe('有氧时间戳状态', () => {
  it('暂停不计时，暂停中结束也不把最后一段暂停计入成绩', () => {
    let state = createCardioState(0)
    state = pauseCardio(state, 10_000)
    expect(cardioElapsedSeconds(state, 15_000)).toBe(10)
    state = resumeCardio(state, 15_000)
    expect(cardioElapsedSeconds(state, 20_000)).toBe(15)
    state = pauseCardio(state, 20_000)
    state = endCardio(state, 25_000)
    expect(cardioElapsedSeconds(state, 30_000)).toBe(15)
  })

  it('序列化恢复后保留开始、暂停和结束状态', () => {
    let state = createCardioState(1_000)
    state = pauseCardio(state, 6_000)
    state = endCardio(state, 11_000)
    const restored = JSON.parse(JSON.stringify(state)) as typeof state
    expect(cardioElapsedSeconds(restored, 60_000)).toBe(5)
    expect(restored.endedAt).toBe(11_000)
  })
})

describe('HIIT 阶段与结果状态机', () => {
  it('正常完成两轮：工作段计轮，休息只累计休息时长', () => {
    let run = createHiitRun(0)
    let transition = completeHiitPhase(plan(), run, 30_000)
    run = transition.run
    expect(run).toMatchObject({ completedRounds: 1, workDone: 30,
      phase: 'rest', status: 'running_rest', round: 1 })
    transition = completeHiitPhase(plan(), run, 50_000)
    run = transition.run
    expect(run).toMatchObject({ completedRounds: 1, restDone: 20,
      phase: 'work', round: 2 })
    run = completeHiitPhase(plan(), run, 80_000).run
    expect(run.completedRounds).toBe(2)
    transition = completeHiitPhase(plan(), run, 100_000)
    expect(transition.run.status).toBe('completed')
    expect(transition.result).toMatchObject({
      duration_seconds: 60,
      hiit: { planned_rounds: 2, completed_rounds: 2,
        work_seconds_done: 60, rest_seconds_done: 40, ended_early: false },
    })
  })

  it('跳过工作段不计完成轮；跳过后续休息仍保留已完成轮', () => {
    let run = skipHiitPhase(plan(), createHiitRun(0), 0).run
    expect(run).toMatchObject({ round: 2, completedRounds: 0,
      skipped: [{ block: 0, round: 1 }] })
    run = completeHiitPhase(plan(), run, 30_000).run
    const transition = skipHiitPhase(plan(), run, 30_000)
    expect(transition.run.status).toBe('completed')
    expect(transition.result).toMatchObject({
      hiit: { completed_rounds: 1, work_seconds_done: 30, rest_seconds_done: 0,
        skipped: [{ block: 0, round: 1 }] },
    })
  })

  it('最后一次跳过工作段也不会丢失 skipped 快照', () => {
    const transition = skipHiitPhase(plan(1), createHiitRun(0), 0)
    expect(transition.run.status).toBe('completed')
    expect(transition.result).toMatchObject({
      duration_seconds: 0,
      hiit: { completed_rounds: 0,
        skipped: [{ block: 0, round: 1 }], ended_early: false },
    })
  })

  it('提前结束计入当前阶段的真实部分时长，但不伪造完成轮', () => {
    const work = stopHiitEarly(plan(), createHiitRun(0), 12_000)
    expect(work.result).toMatchObject({
      duration_seconds: 12,
      hiit: { completed_rounds: 0, work_seconds_done: 12,
        rest_seconds_done: 0, ended_early: true },
    })
    const resting = completeHiitPhase(plan(), createHiitRun(0), 30_000).run
    const rest = stopHiitEarly(plan(), resting, 38_000)
    expect(rest.result).toMatchObject({
      hiit: { completed_rounds: 1, work_seconds_done: 30,
        rest_seconds_done: 8, ended_early: true },
    })
  })

  it('用户暂停期间不推进阶段，恢复后从剩余时间继续', () => {
    let run = pauseHiit(createHiitRun(0), 10_000)
    expect(hiitPhaseElapsed(run, 60_000)).toBe(10)
    run = resumeHiit(run, 20_000)
    expect(hiitPhaseElapsed(run, 30_000)).toBe(20)
    expect(run.status).toBe('running_work')
  })

  it('正常计时自动推进；长间隔或刷新后的跨阶段需要确认', () => {
    const run = createHiitRun(0)
    expect(needsHiitConfirmation(run, plan(), 30_000, 250)).toBe(false)
    expect(needsHiitConfirmation(run, plan(), 60_000, 5_000)).toBe(true)
    expect(needsHiitConfirmation(run, plan(), 60_000, 0)).toBe(true)
  })
})
