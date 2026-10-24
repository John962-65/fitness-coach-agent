// 逐组记录的统一文案（Workout 组表 / 历史 / 我的表现共用）
import type { SetLog } from '../types'

export function formatSetRecord(l: { type?: SetLog['type']; weight_kg?: number | null;
  reps?: number | null; rpe?: number | null; added_weight_kg?: number | null;
  assistance_kg?: number | null; duration_seconds?: number | null;
  distance_m?: number | null }): string {
  const t = l.type || 'weight_reps'
  switch (t) {
    case 'duration': {
      const s = l.duration_seconds || 0
      return `${Math.floor(s / 60)} 分 ${s % 60} 秒`
    }
    case 'distance_time': {
      const s = l.duration_seconds || 0
      return `${l.distance_m ?? '?'} 米 · ${Math.floor(s / 60)} 分 ${s % 60} 秒`
    }
    case 'bodyweight_reps':
      return `${l.reps ?? '?'} 次${l.added_weight_kg ? `（+${l.added_weight_kg} kg）` : '（自重）'}`
    case 'assisted_reps':
      return `${l.reps ?? '?'} 次（辅助 ${l.assistance_kg ?? '?'} kg）`
    default:
      return `${l.weight_kg ?? '?'} kg × ${l.reps ?? '?'} 次`
  }
}

/** 供保存 raw 文本使用的紧凑写法 */
export function formatSetCompact(l: SetLog): string {
  const t = l.type || 'weight_reps'
  switch (t) {
    case 'duration': {
      const s = l.duration_seconds || 0
      return `${Math.floor(s / 60)}分${s % 60}秒`
    }
    case 'distance_time': {
      const s = l.duration_seconds || 0
      return `${l.distance_m ?? '?'}m-${Math.floor(s / 60)}分${s % 60}秒`
    }
    case 'bodyweight_reps':
      return `${l.reps ?? '?'}次${l.added_weight_kg ? `+${l.added_weight_kg}kg` : ''}`
    case 'assisted_reps':
      return `${l.reps ?? '?'}次辅助${l.assistance_kg ?? '?'}kg`
    default:
      return `${l.weight_kg ?? '?'}kg×${l.reps ?? '?'}`
  }
}
