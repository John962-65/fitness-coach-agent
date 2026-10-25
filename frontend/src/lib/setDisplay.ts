// 逐组记录的统一文案（Workout 组表 / 历史 / 我的表现共用）
import type { SetLog } from '../types'

export function formatSetRecord(l: { type?: SetLog['type']; weight_kg?: number | null;
  reps?: number | null; rpe?: number | null; added_weight_kg?: number | null;
  assistance_kg?: number | null; duration_seconds?: number | null;
  distance_m?: number | null;
  method?: string | null; segments?: Record<string, unknown>[] | null }): string {
  const METHOD_LABEL: Record<string, string> = {
    drop_set: '递减', rest_pause: '休息暂停', unilateral: '单侧',
  }
  const segText = (l.method && Array.isArray(l.segments) && l.segments.length)
    ? l.segments.map((sg) => {
        const seg = sg as Record<string, number | string>
        const w = seg.weight_kg != null ? `${seg.weight_kg}kg` : ''
        const side = seg.side === 'left' ? '左' : seg.side === 'right' ? '右' : ''
        const rest = seg.rest_seconds != null ? `歇${seg.rest_seconds}s` : ''
        return `${side}${w}${seg.reps ?? '?'}次${rest}`
      }).join(' + ')
    : null
  const t = l.type || 'weight_reps'
  const base = (() => {
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
  })()
  if (segText) return `${METHOD_LABEL[l.method ?? ''] ?? ''}：${segText}`
  if (l.method && l.method !== 'straight_set') {
    return `${METHOD_LABEL[l.method]} · ${base}`
  }
  return base
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
