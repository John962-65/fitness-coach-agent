// M6.1 P0：纠错必须保留逐组记录——锁定 buildCorrectedData 的聚合/保留规则
import { describe, expect, it } from 'vitest'
import { buildCorrectedData, deriveAggregates, rebuildTrainingRaw } from './checkin'
import type { Checkin } from '../types'

const checkin = (data: Checkin['data'], type = 'training'): Checkin =>
  ({ id: 1, revision: 0, type, data, at: '2026-10-24T10:00:00Z' }) as Checkin

describe('deriveAggregates（与后端 save_checkin P0-4 规则一致）', () => {
  it('代表组 = 正式组中容量最大者', () => {
    const logs = [
      { weight_kg: 60, reps: 10 },
      { weight_kg: 65, reps: 8 },
      { weight_kg: 70, reps: 6 },
    ]
    expect(deriveAggregates(logs)).toEqual({ sets: 3, weight_kg: 60, reps: 10, rpe: undefined })
  })

  it('容量并列取重量更大者', () => {
    const logs = [
      { weight_kg: 80, reps: 5 },   // 400
      { weight_kg: 100, reps: 4 },  // 400，更重 → 代表
    ]
    expect(deriveAggregates(logs)).toMatchObject({ weight_kg: 100, reps: 4 })
  })

  it('热身组不计入；全热身返回 null', () => {
    expect(deriveAggregates([
      { weight_kg: 20, reps: 10, warmup: true },
      { weight_kg: 60, reps: 8 },
    ])).toMatchObject({ sets: 1, weight_kg: 60, reps: 8 })
    expect(deriveAggregates([{ weight_kg: 20, reps: 10, warmup: true }])).toBeNull()
  })
})

describe('buildCorrectedData（P0：纠错不丢逐组）', () => {
  const data = {
    exercises: [{
      name: '杠铃平板卧推',
      exercise_id: 'barbell_bench_press',
      sets: 3, weight_kg: 60, reps: 10,
      set_logs: [
        { weight_kg: 60, reps: 10, warmup: false, at: '2026-10-24T10:01:00Z' },
        { weight_kg: 65, reps: 8, warmup: false, at: '2026-10-24T10:05:00Z' },
        { weight_kg: 70, reps: 6, warmup: false, at: '2026-10-24T10:09:00Z' },
      ],
    }],
    raw: '周六：杠铃平板卧推 3 组：60kg×10、65kg×8、70kg×6。备注：感觉良好',
  }

  it('只改第二组重量：其余组、热身标记、时间戳、exercise_id 原样保留', () => {
    const out = buildCorrectedData(checkin(data), [
      { logs: [
        { weight: '60', reps: '10', rpe: '' },
        { weight: '67.5', reps: '8', rpe: '' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    expect(out).not.toBeNull()
    const ex = out!.exercises![0]
    expect(ex.set_logs).toHaveLength(3)
    expect(ex.set_logs![1].weight_kg).toBe(67.5)
    expect(ex.set_logs![1].at).toBe('2026-10-24T10:05:00Z')   // 时间戳保留
    expect(ex.set_logs![0]).toEqual(data.exercises[0].set_logs[0]) // 未改动组原样
    expect(ex.exercise_id).toBe('barbell_bench_press')
  })

  it('聚合字段按代表组重建（改后 67.5×10=675 成为最大容量）', () => {
    const out = buildCorrectedData(checkin(data), [
      { logs: [
        { weight: '60', reps: '10', rpe: '' },
        { weight: '67.5', reps: '10', rpe: '8' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    const ex = out!.exercises![0]
    expect(ex.sets).toBe(3)
    expect(ex.weight_kg).toBe(67.5)
    expect(ex.reps).toBe(10)
    expect(ex.rpe).toBe(8)
  })

  it('raw 重写为纠正后的逐组文本，保留日期前缀与备注', () => {
    const out = buildCorrectedData(checkin(data), [
      { logs: [
        { weight: '60', reps: '10', rpe: '' },
        { weight: '67.5', reps: '8', rpe: '' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    expect(out!.raw).toBe('周六：杠铃平板卧推 3 组：60kg×10、67.5kg×8、70kg×6。备注：感觉良好')
  })

  it('清空某组重量 = 显式置 null；非法数字返回 null 拦截提交', () => {
    const out = buildCorrectedData(checkin(data), [
      { logs: [
        { weight: '', reps: '10', rpe: '' },
        { weight: '65', reps: '8', rpe: '' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    expect(out!.exercises![0].set_logs![0].weight_kg).toBeNull()

    const bad = buildCorrectedData(checkin(data), [
      { logs: [
        { weight: 'abc', reps: '10', rpe: '' },
        { weight: '65', reps: '8', rpe: '' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    expect(bad).toBeNull()
  })

  it('未知字段与 raw 之外的顶层字段原样保留', () => {
    const withExtra = { ...data, source: 'web', coach_note: 'keep me' }
    const out = buildCorrectedData(checkin(withExtra), [
      { logs: [
        { weight: '60', reps: '10', rpe: '' },
        { weight: '65', reps: '8', rpe: '' },
        { weight: '70', reps: '6', rpe: '' },
      ] },
    ])
    expect(out!.source).toBe('web')
    expect(out!.coach_note).toBe('keep me')
  })

  it('旧聚合记录（无 set_logs）按整动作编辑；body 类型不改写 raw', () => {
    const legacy = { exercises: [{ name: '跑步', weight_kg: 0, reps: 1 }], raw: '跑了 5 公里' }
    const out = buildCorrectedData(checkin(legacy), [{ weight: '', reps: '1' }])
    expect(out!.exercises![0]).toEqual({ name: '跑步', reps: 1 }) // weight_kg 被显式清空
    expect(out!.raw).toBe('跑了 5 公里')

    const body = buildCorrectedData(checkin({ weight_kg: 72 }, 'body'), [])
    expect(body!.raw).toBeUndefined()
  })
})

describe('rebuildTrainingRaw', () => {
  it('无前缀/无备注的原文也能重建', () => {
    expect(rebuildTrainingRaw('训练：卧推 1 组：60kg×10', [{ name: '卧推', logs: [{ weight_kg: 62, reps: 10 }] }]))
      .toBe('训练：卧推 1 组：62kg×10')
  })
  it('全部热身（无正式组）时保留原文', () => {
    expect(rebuildTrainingRaw('周六：卧推', [{ name: '卧推', logs: [{ weight_kg: 20, reps: 10, warmup: true }] }]))
      .toBe('周六：卧推')
  })
})


describe('M6.4-A.1：分型纠错', () => {
  const mixed: Checkin['data'] = {
    exercises: [
      { name: '杠铃平板卧推', exercise_id: 'barbell_bench_press',
        sets: 1, weight_kg: 60, reps: 10,
        set_logs: [{ type: 'weight_reps', weight_kg: 60, reps: 10,
                     warmup: false, at: '2026-10-25T10:00:00' }] },
      { name: '引体向上', exercise_id: 'pull_up',
        sets: 1, weight_kg: 5, reps: 8,
        set_logs: [{ type: 'bodyweight_reps', reps: 8, added_weight_kg: 5,
                     warmup: false, at: '2026-10-25T10:03:00' }] },
      { name: '平板支撑', exercise_id: 'plank',
        sets: 1,
        set_logs: [{ type: 'duration', duration_seconds: 90,
                     warmup: false, at: '2026-10-25T10:06:00' }] },
    ],
    raw: '训练：卧推 1 组：60kg×10；引体 1 组：8次+5kg；平板 1 组：1分30秒',
  }

  it('修改引体额外负重：类型/时间戳保留，聚合按分型重建', () => {
    const empty = {}
    const out = buildCorrectedData(checkin(mixed), [
      empty,
      { logs: [{ reps: '8', added: '7.5', rpe: '' }] },
      empty,
    ] as Parameters<typeof buildCorrectedData>[1])
    expect(out).not.toBeNull()
    const pull = out!.exercises![1]
    expect(pull.set_logs![0].added_weight_kg).toBe(7.5)
    expect(pull.set_logs![0].type).toBe('bodyweight_reps')
    expect(pull.set_logs![0].at).toBe('2026-10-25T10:03:00')
    expect(pull.weight_kg).toBe(7.5)          // 聚合负荷 = 额外负重
    // 卧推与平板未触碰，原样
    expect(out!.exercises![0]).toEqual(mixed.exercises![0])
    expect(out!.exercises![2]).toEqual(mixed.exercises![2])
  })

  it('修改平板时长：duration_seconds 按分秒重建，raw 同步', () => {
    const empty = {}
    const out = buildCorrectedData(checkin(mixed), [
      empty, empty,
      { logs: [{ minutes: '2', seconds: '15' }] },
    ] as Parameters<typeof buildCorrectedData>[1])
    const plank = out!.exercises![2]
    expect(plank.set_logs![0].duration_seconds).toBe(135)
    expect(out!.raw).toContain('2分15秒')
    expect(out!.raw).toContain('60kg×10')     // 未触碰组原样出现在 raw（紧凑文案）
  })
})
