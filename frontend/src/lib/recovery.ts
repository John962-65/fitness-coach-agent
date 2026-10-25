// 恢复量表：1-5 分，方向全局统一（与后端 SCALE_LABELS 同文案，禁止相反计分）
export const RECOVERY_SCALES: { key: string; label: string; levels: Record<number, string> }[] = [
  { key: 'sleep_quality', label: '睡眠质量',
    levels: { 1: '非常差', 2: '较差', 3: '一般', 4: '较好', 5: '非常好' } },
  { key: 'fatigue', label: '疲劳程度',
    levels: { 1: '几乎不疲劳', 2: '略感疲劳', 3: '中等疲劳', 4: '比较疲劳', 5: '非常疲劳' } },
  { key: 'muscle_soreness', label: '肌肉酸痛',
    levels: { 1: '几乎不酸', 2: '轻微酸痛', 3: '明显酸痛', 4: '比较严重', 5: '非常严重' } },
  { key: 'training_readiness', label: '训练意愿',
    levels: { 1: '完全不想练', 2: '不太想练', 3: '一般', 4: '比较想练', 5: '状态很好想练' } },
]

export const SORENESS_REGIONS = ['肩', '肘', '腕', '腰背', '髋', '膝', '踝', '颈', '其他']

export function scaleText(key: string, v: number | null | undefined): string {
  if (v == null) return '—'
  const scale = RECOVERY_SCALES.find((s) => s.key === key)
  return `${v}/5${scale ? `（${scale.levels[v]}）` : ''}`
}
