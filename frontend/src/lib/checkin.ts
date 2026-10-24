// 纠错载荷构建（M6.1 P0 修复）：
// 历史"纠错"必须保留逐组记录（set_logs/热身标记/完成时间），只更新用户明确修改的字段；
// 聚合字段（sets/weight_kg/reps/rpe）按后端 save_checkin 的同一规则重建
// （backend/routes.py P0-4：代表组 = 正式组中容量最大者，并列取重量更大、先出现者）。
import type { Checkin, CheckinExercise, SetLog } from '../types'

/** 一组可编辑字段（空字符串 = 用户清空该值） */
export interface SetEdit {
  weight: string
  reps: string
  rpe: string
}

export interface ExerciseEdit {
  /** 逐组模式：与原 set_logs 一一对应 */
  logs?: SetEdit[]
  /** 旧聚合模式（无 set_logs 的历史记录）：整动作 weight/reps */
  weight?: string
  reps?: string
}

const num = (s: string | undefined): number | null | undefined => {
  if (s === undefined) return undefined
  if (s.trim() === '') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : undefined // undefined = 非法输入，由调用方拦截
}

/** 与后端 save_checkin 相同的聚合派生：无正式组时返回 null（调用方应删除聚合字段） */
export function deriveAggregates(logs: SetLog[]): {
  sets: number; weight_kg: number | null | undefined; reps: number | null | undefined; rpe: number | null | undefined
} | null {
  const main = logs.filter((l) => !l.warmup)
  if (!main.length) return null
  const best = main.reduce((a, b) => {
    const va = (a.weight_kg ?? 0) * (a.reps ?? 0)
    const vb = (b.weight_kg ?? 0) * (b.reps ?? 0)
    if (vb !== va) return vb > va ? b : a
    return (b.weight_kg ?? 0) > (a.weight_kg ?? 0) ? b : a
  })
  return { sets: main.length, weight_kg: best.weight_kg, reps: best.reps, rpe: best.rpe }
}

/** 重建训练 raw 文本：保留原"日期前缀"与"备注"段，中间按纠正后的正式组重写 */
export function rebuildTrainingRaw(
  origRaw: string | undefined,
  exercises: { name: string; logs: SetLog[] }[],
): string | undefined {
  const orig = origRaw || ''
  const notesAt = orig.indexOf('。备注：')
  const notes = notesAt >= 0 ? orig.slice(notesAt + '。备注：'.length) : ''
  const colonAt = orig.indexOf('：')
  const prefix = colonAt >= 0 ? orig.slice(0, colonAt + 1) : '训练：'
  const lines = exercises
    .filter((e) => e.logs.some((l) => !l.warmup))
    .map((e) => {
      const main = e.logs.filter((l) => !l.warmup)
      return `${e.name} ${main.length} 组：` + main
        .map((l) => `${l.weight_kg ?? '?'}kg×${l.reps ?? '?'}`).join('、')
    })
  if (!lines.length) return origRaw // 全部为热身/无正式组时保留原文
  return `${prefix}${lines.join('；')}${notes ? `。备注：${notes}` : ''}`
}

/**
 * 构建纠错提交的完整 data：
 * - 逐组动作：每组仅当输入与原值不同才覆盖对应字段（weight/reps/rpe），
 *   热身标记与 at 时间戳永远原样保留
 * - 旧聚合动作（无 set_logs）：沿用整动作编辑
 * - 其余字段（raw 之外的未知字段、exercise_id 等）原样保留
 * 返回 null 表示存在非法数字输入（调用方展示校验错误，不提交）。
 */
export function buildCorrectedData(
  checkin: Checkin,
  edits: ExerciseEdit[],
): Checkin['data'] | null {
  const origExercises = checkin.data.exercises || []
  const exercises: CheckinExercise[] = []
  for (let i = 0; i < origExercises.length; i++) {
    const orig = origExercises[i]
    const edit = edits[i] || {}
    const next: CheckinExercise = { ...orig }
    if (Array.isArray(orig.set_logs) && orig.set_logs.length > 0) {
      const logs: SetLog[] = []
      for (let j = 0; j < orig.set_logs.length; j++) {
        const l = orig.set_logs[j]
        const e = edit.logs?.[j]
        // M6.4-A：非 weight_reps 类型（时长/距离等）暂不支持逐字段纠错，原样保留
        if (!e || (l.type && l.type !== 'weight_reps')) { logs.push(l); continue }
        const weight = num(e.weight)
        const reps = num(e.reps)
        const rpe = num(e.rpe)
        if (weight === undefined || reps === undefined || rpe === undefined) return null
        const nextLog = { ...l }
        // 只覆盖与原值不同的字段：未触碰的字段（含未录入的 rpe）原样保留
        if (e.weight !== (l.weight_kg != null ? String(l.weight_kg) : ''))
          nextLog.weight_kg = weight ?? null
        if (e.reps !== (l.reps != null ? String(l.reps) : ''))
          nextLog.reps = reps ?? null
        if (e.rpe !== (l.rpe != null ? String(l.rpe) : ''))
          nextLog.rpe = rpe ?? null
        logs.push(nextLog)
      }
      next.set_logs = logs
      const agg = deriveAggregates(logs)
      if (agg) {
        next.sets = agg.sets
        // 与后端 save_checkin 一致：代表组的值可能为 null（显式清空）
        next.weight_kg = agg.weight_kg as number | undefined
        next.reps = agg.reps as number | undefined
        next.rpe = agg.rpe as number | undefined
      } else {
        delete next.weight_kg
        delete next.reps
        delete next.sets
        delete next.rpe
      }
    } else {
      const weight = num(edit.weight)
      const reps = num(edit.reps)
      if (weight === undefined || reps === undefined) return null
      if (weight === null) delete next.weight_kg
      else next.weight_kg = weight
      if (reps === null) delete next.reps
      else next.reps = reps
    }
    exercises.push(next)
  }
  const data: Checkin['data'] = { ...checkin.data, exercises }
  if (checkin.type === 'training') {
    data.raw = rebuildTrainingRaw(
      checkin.data.raw,
      exercises.map((e) => ({ name: e.name, logs: e.set_logs || [] })),
    ) ?? checkin.data.raw
  }
  return data
}
