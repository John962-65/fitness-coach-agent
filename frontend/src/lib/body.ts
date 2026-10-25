// 身体数据展示工具（与后端 body_metrics 口径一致：NULL=未测量，不显示 0）
import type { BodyMetricKey } from '../types'

export const BODY_METRICS: { key: BodyMetricKey; label: string; unit: string }[] = [
  { key: 'weight_kg', label: '体重', unit: 'kg' },
  { key: 'waist_cm', label: '腰围', unit: 'cm' },
  { key: 'hip_cm', label: '臀围', unit: 'cm' },
  { key: 'chest_cm', label: '胸围', unit: 'cm' },
  { key: 'body_fat_percent', label: '体脂率', unit: '%' },
  { key: 'muscle_mass_kg', label: '肌肉量', unit: 'kg' },
]

export const MEASUREMENT_METHODS: { key: string; label: string; note: string }[] = [
  { key: 'home_scale', label: '家用体重秤/体脂秤', note: '体脂为估算，误差随水分变化' },
  { key: 'gym_scale', label: '健身房秤', note: '建议同设备同状态比较' },
  { key: 'tape', label: '皮尺围度', note: '手法差异 ±1-2cm' },
  { key: 'caliper', label: '皮褶钳', note: '依赖测量手法' },
  { key: 'dexa', label: 'DEXA 扫描', note: '参考精度较高' },
  { key: 'bia', label: '生物电阻抗', note: '受水分/进食/时间影响' },
  { key: 'other', label: '其他', note: '' },
]

export const METHOD_LABEL: Record<string, string> = Object.fromEntries(
  MEASUREMENT_METHODS.map((m) => [m.key, m.label]))

export function fmtNum(v: number | null | undefined, unit = ''): string {
  if (v === null || v === undefined) return '—'
  const n = Number.isInteger(v) ? String(v) : v.toFixed(1)
  return `${n}${unit}`
}

export function fmtDelta(v: number | null | undefined, unit = ''): string {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${Number.isInteger(v) ? v : v.toFixed(1)}${unit}`
}

export function sourceRefText(src: string): string {
  const m = /^body:(\d+):revision:(\d+)$/.exec(src)
  if (!m) return src
  return `测量 #${m[1]}${Number(m[2]) > 0 ? `（修订 ${m[2]}）` : ''}`
}
