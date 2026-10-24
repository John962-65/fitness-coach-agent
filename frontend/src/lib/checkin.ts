// 纠错载荷构建（M6.1 P0 修复）：
// 历史"纠错"必须保留逐组记录（set_logs/热身标记/完成时间），只更新用户明确修改的字段；
// 聚合字段（sets/weight_kg/reps/rpe）按后端 save_checkin 的同一规则重建
// （backend/routes.py P0-4：代表组 = 正式组中容量最大者，并列取重量更大、先出现者）。
import { formatSetCompact } from './setDisplay'
import type { Checkin, CheckinExercise, SetLog } from '../types'

/** 一组可编辑字段（按记录类型取用；空字符串 = 用户清空该值） */
export interface SetEdit {
  weight?: string
  reps?: string
  rpe?: string
  added?: string     // bodyweight_reps 额外负重
  assist?: string    // assisted_reps 辅助重量
  minutes?: string   // duration / distance_time
  seconds?: string
  distance?: string  // distance_time
}

/** 从原记录初始化编辑值（M6.4-A.1：与训练执行同口径的分型输入） */
export function initSetEdit(l: SetLog): SetEdit {
  const t = l.type || 'weight_reps'
  if (t === 'duration') {
    const sec = l.duration_seconds || 0
    return { minutes: String(Math.floor(sec / 60)), seconds: String(sec % 60) }
  }
  if (t === 'distance_time') {
    const sec = l.duration_seconds || 0
    return { distance: l.distance_m != null ? String(l.distance_m) : '',
             minutes: String(Math.floor(sec / 60)), seconds: String(sec % 60) }
  }
  if (t === 'bodyweight_reps')
    return { reps: l.reps != null ? String(l.reps) : '',
             added: l.added_weight_kg != null ? String(l.added_weight_kg) : '',
             rpe: l.rpe != null ? String(l.rpe) : '' }
  if (t === 'assisted_reps')
    return { reps: l.reps != null ? String(l.reps) : '',
             assist: l.assistance_kg != null ? String(l.assistance_kg) : '',
             rpe: l.rpe != null ? String(l.rpe) : '' }
  return { weight: l.weight_kg != null ? String(l.weight_kg) : '',
           reps: l.reps != null ? String(l.reps) : '',
           rpe: l.rpe != null ? String(l.rpe) : '' }
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

/** 单组负荷（kg）：bodyweight_reps = 额外负重（自重不可比）；其余 = weight_kg。
 *  与后端 save_checkin 的 _load 同口径（M6.4-A.1）。 */
function logLoad(l: SetLog): number | null | undefined {
  return l.type === 'bodyweight_reps' ? l.added_weight_kg : l.weight_kg
}

/** 与后端 save_checkin 相同的聚合派生：无正式组时返回 null（调用方应删除聚合字段） */
export function deriveAggregates(logs: SetLog[]): {
  sets: number; weight_kg: number | null | undefined; reps: number | null | undefined; rpe: number | null | undefined
} | null {
  const main = logs.filter((l) => !l.warmup)
  if (!main.length) return null
  const load = (l: SetLog) => logLoad(l) ?? 0
  const best = main.reduce((a, b) => {
    const va = load(a) * (a.reps ?? 0)
    const vb = load(b) * (b.reps ?? 0)
    if (vb !== va) return vb > va ? b : a
    return load(b) > load(a) ? b : a
  })
  return { sets: main.length, weight_kg: logLoad(best), reps: best.reps, rpe: best.rpe }
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
      return `${e.name} ${main.length} 组：` + main.map(formatSetCompact).join('、')
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
        if (!e) { logs.push(l); continue }
        const t = l.type || 'weight_reps'
        const nextLog: SetLog = { ...l }
        const changed = (cur: number | null | undefined, v?: string) =>
          v !== (cur != null ? String(cur) : '')
        // M6.4-A.1：按类型只覆盖与原值不同的字段；type/at/warmup 永远原样保留
        if (t === 'duration') {
          const m = num(e.minutes); const sec = num(e.seconds)
          if (m === undefined || sec === undefined) return null
          if (changed(l.duration_seconds, e.minutes) || changed(l.duration_seconds, e.seconds))
            nextLog.duration_seconds = (m ?? 0) * 60 + (sec ?? 0)
        } else if (t === 'distance_time') {
          const d = num(e.distance); const m = num(e.minutes); const sec = num(e.seconds)
          if (d === undefined || m === undefined || sec === undefined) return null
          if (changed(l.distance_m, e.distance)) nextLog.distance_m = d ?? null
          if (changed(l.duration_seconds, e.minutes) || changed(l.duration_seconds, e.seconds))
            nextLog.duration_seconds = (m ?? 0) * 60 + (sec ?? 0)
        } else if (t === 'bodyweight_reps') {
          const reps = num(e.reps); const added = num(e.added)
          if (reps === undefined || added === undefined) return null
          if (changed(l.reps, e.reps)) nextLog.reps = reps ?? null
          if (changed(l.added_weight_kg, e.added)) nextLog.added_weight_kg = added ?? null
        } else if (t === 'assisted_reps') {
          const reps = num(e.reps); const a = num(e.assist)
          if (reps === undefined || a === undefined) return null
          if (changed(l.reps, e.reps)) nextLog.reps = reps ?? null
          if (changed(l.assistance_kg, e.assist)) nextLog.assistance_kg = a ?? null
        } else {
          const weight = num(e.weight)
          const reps = num(e.reps)
          const rpe = num(e.rpe)
          if (weight === undefined || reps === undefined || rpe === undefined) return null
          if (changed(l.weight_kg, e.weight)) nextLog.weight_kg = weight ?? null
          if (changed(l.reps, e.reps)) nextLog.reps = reps ?? null
          if (changed(l.rpe, e.rpe)) nextLog.rpe = rpe ?? null
        }
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
