// 统一修改协议（TASKBOOK_2.0 §三/B2）的客户端操作构造器。
// 前端只构造类型化操作，校验与提交全部在后端（同套规则，前端不复制校验逻辑）。
import type { PlanOp } from '../types'

export const addExercise = (
  day: string, exercise: string, sets: number | string, reps: number | string,
  extra: Partial<Extract<PlanOp, { op: 'add_exercise' }>> = {},
): PlanOp => ({ op: 'add_exercise', day, exercise, sets, reps, ...extra })

export const removeByIndex = (day: string, index: number): PlanOp =>
  ({ op: 'remove_exercise', day, index })

export const removeByName = (day: string, exercise: string): PlanOp =>
  ({ op: 'remove_exercise', day, exercise })

export const replaceByIndex = (
  day: string, index: number, newExercise: string,
  extra: Partial<Extract<PlanOp, { op: 'replace_exercise' }>> = {},
): PlanOp => ({ op: 'replace_exercise', day, index, exercise: newExercise, ...extra })

export const reorder = (day: string, from: number, to: number): PlanOp =>
  ({ op: 'reorder_exercise', day, from, to })

export const editPrescription = (
  day: string, index: number,
  patch: { sets?: number | string; reps?: number | string; weight_kg?: number; note?: string },
): PlanOp => ({ op: 'edit_set_prescription', day, index, ...patch })

export const renameDay = (day: string, newName: string): PlanOp =>
  ({ op: 'rename_day', day, new_name: newName })
