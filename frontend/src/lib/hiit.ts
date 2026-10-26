import { CUSTOM_HIIT_EXERCISE_ID } from './exerciseIds'
import type { HiitPlan } from '../types'

export function hiitPlanExerciseId(plan: HiitPlan): string {
  if (plan.exercise_id) return plan.exercise_id
  if (plan.blocks.length === 1 && plan.blocks[0].exercise_id) {
    return plan.blocks[0].exercise_id
  }
  return CUSTOM_HIIT_EXERCISE_ID
}
