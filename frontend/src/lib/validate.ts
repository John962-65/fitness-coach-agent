// 训练数据统一校验规则（M6.1.1）：
// 训练执行记录（Workout）与历史纠错（History）共用同一套范围约束，
// 避免两处口径漂移。返回 null 表示通过，返回字符串为可直接展示的错误。
export const TRAINING_LIMITS = {
  weightMin: 0, // 仅允许 >0（自重动作请留空，用 null 表示）
  weightMax: 500,
  repsMin: 1,
  repsMax: 100,
  rpeMin: 1,
  rpeMax: 10,
} as const

export function validateWeight(kg: number | null): string | null {
  if (kg == null) return null
  if (kg <= TRAINING_LIMITS.weightMin || kg > TRAINING_LIMITS.weightMax)
    return `重量需在 ${TRAINING_LIMITS.weightMin + 0.01}-${TRAINING_LIMITS.weightMax} kg 之间（自重动作请留空）`
  return null
}

export function validateReps(reps: number | null, warmup: boolean): string | null {
  if (reps == null) return warmup ? null : '正式组请填写次数（≥1）'
  if (!Number.isInteger(reps)) return '次数需为整数'
  if (reps < TRAINING_LIMITS.repsMin || reps > TRAINING_LIMITS.repsMax)
    return `次数需为 ${TRAINING_LIMITS.repsMin}-${TRAINING_LIMITS.repsMax} 的整数`
  return null
}

export function validateRpe(rpe: number | null): string | null {
  if (rpe == null) return null
  if (rpe < TRAINING_LIMITS.rpeMin || rpe > TRAINING_LIMITS.rpeMax)
    return `RPE 取值范围 ${TRAINING_LIMITS.rpeMin}-${TRAINING_LIMITS.rpeMax}`
  return null
}

/** 一组输入的合并校验；返回第一条错误或 null */
export function validateSetValues(
  weight: number | null, reps: number | null, rpe: number | null, warmup: boolean,
): string | null {
  return validateWeight(weight) || validateReps(reps, warmup) || validateRpe(rpe)
}

/** 文本 → 数字（空串=null，非法=undefined）；供调用方先判型再校验范围 */
export function parseTrainingNumber(s: string): number | null | undefined {
  const t = s.trim()
  if (t === '') return null
  const n = Number(t)
  return Number.isFinite(n) ? n : undefined
}

// ---- M6.4-A：分型逐组校验（不同记录类型不同规则，绝不混用） ----
import type { MeasurementType } from '../types'

export interface SetDraft {
  type: MeasurementType
  weight?: number | null
  reps?: number | null
  added?: number | null
  assist?: number | null
  minutes?: number | null
  seconds?: number | null
  distance?: number | null
  rpe?: number | null
}

export function validateSetDraft(d: SetDraft): string | null {
  if (d.rpe != null && (d.rpe < TRAINING_LIMITS.rpeMin || d.rpe > TRAINING_LIMITS.rpeMax))
    return `RPE 取值范围 ${TRAINING_LIMITS.rpeMin}-${TRAINING_LIMITS.rpeMax}`
  const repsErr = (required: boolean) => {
    if (d.reps == null) return required ? '请填写次数' : null
    if (!Number.isInteger(d.reps)) return '次数需为整数'
    if (d.reps < TRAINING_LIMITS.repsMin || d.reps > TRAINING_LIMITS.repsMax)
      return `次数需为 ${TRAINING_LIMITS.repsMin}-${TRAINING_LIMITS.repsMax} 的整数`
    return null
  }
  const loadErr = (label: string, v: number | null | undefined, required: boolean) => {
    if (v == null) return required ? `请填写${label}` : null
    if (v < 0 || v > TRAINING_LIMITS.weightMax) return `${label}需在 0-${TRAINING_LIMITS.weightMax} 之间`
    return null
  }
  switch (d.type) {
    case 'weight_reps': {
      if (d.weight != null && (d.weight <= 0 || d.weight > TRAINING_LIMITS.weightMax))
        return `重量需在 0.01-${TRAINING_LIMITS.weightMax} kg 之间（自重动作请留空）`
      return repsErr(true)
    }
    case 'bodyweight_reps': {
      const e1 = repsErr(true)
      if (e1) return e1
      return loadErr('额外负重', d.added, false)
    }
    case 'assisted_reps': {
      const e1 = repsErr(true)
      if (e1) return e1
      return loadErr('辅助重量', d.assist, true)
    }
    case 'duration': {
      const total = (d.minutes || 0) * 60 + (d.seconds || 0)
      if (total < 1) return '请填写持续时间'
      if (total > 7200) return '单组持续时间不超过 120 分钟'
      return null
    }
    case 'distance_time': {
      if (d.distance == null || d.distance < 1 || d.distance > 200000)
        return '距离需在 1-200000 米之间'
      const total = (d.minutes || 0) * 60 + (d.seconds || 0)
      if (total < 1) return '请填写用时'
      if (total > 7200 * 6) return '单组用时不超过 12 小时'
      return null
    }
  }
}
