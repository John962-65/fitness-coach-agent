import { describe, expect, it } from 'vitest'
import { addExercise, editPrescription, removeByIndex,
         replaceByIndex, reorder, renameDay } from './protocol'

// 客户端只构造类型化操作，形状必须与后端 coach/plan_edit.py PLAN_OPS 对齐
describe('plan protocol builders', () => {
  it('add_exercise carries day/exercise/prescription', () => {
    expect(addExercise('周一', 'plank', 3, '45秒', { note: '核心' })).toEqual({
      op: 'add_exercise', day: '周一', exercise: 'plank', sets: 3, reps: '45秒', note: '核心',
    })
  })

  it('remove / replace / reorder / rename / edit shapes', () => {
    expect(removeByIndex('周一', 2)).toEqual({ op: 'remove_exercise', day: '周一', index: 2 })
    expect(replaceByIndex('周一', 0, 'goblet_squat')).toEqual({
      op: 'replace_exercise', day: '周一', index: 0, exercise: 'goblet_squat',
    })
    expect(reorder('周一', 1, 0)).toEqual({ op: 'reorder_exercise', day: '周一', from: 1, to: 0 })
    expect(renameDay('周一', '推日')).toEqual({ op: 'rename_day', day: '周一', new_name: '推日' })
    expect(editPrescription('周一', 0, { sets: 4, weight_kg: 60 })).toEqual({
      op: 'edit_set_prescription', day: '周一', index: 0, sets: 4, weight_kg: 60,
    })
  })
})
