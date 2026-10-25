// 专家平台展示工具：状态/置信度标签与配色（与后端状态机一致，纯函数可测）

export const INSIGHT_STATUS: Record<string, { label: string; tone: string }> = {
  ready: { label: '新分析', tone: 'bg-accent-soft text-accent-deep' },
  viewed: { label: '已读', tone: 'bg-ink/5 text-muted' },
  dismissed: { label: '已忽略', tone: 'bg-ink/5 text-faint' },
  expired: { label: '已过期', tone: 'bg-amber-50 text-amber-700' },
  invalidated: { label: '已失效', tone: 'bg-red-50 text-red-600' },
  failed: { label: '失败', tone: 'bg-red-50 text-red-600' },
}

export const CONFIDENCE: Record<string, { label: string; tone: string; note: string }> = {
  high: { label: '数据充分', tone: 'bg-emerald-50 text-emerald-700',
          note: '窗口内 ≥4 次记录、无纠错、间隔连续' },
  medium: { label: '数据一般', tone: 'bg-amber-50 text-amber-700',
            note: '窗口内 2-3 次记录，或存在纠错/间隔' },
  low: { label: '数据有限', tone: 'bg-red-50 text-red-600',
         note: '仅 1 次记录，只有基本盘事实、无趋势比较' },
}

export const TASK_STATUS: Record<string, string> = {
  pending: '排队中', running: '分析中', ready: '完成',
  failed: '失败', cancelled: '已取消',
}

export const SPECIALIST_LABEL: Record<string, string> = {
  training_science: '训练科学', nutrition: '营养', recovery: '恢复',
  rehabilitation: '康复与伤痛风险', movement: '动作技术',
}

export const FINDING_KIND: Record<string, string> = {
  'session-baseline': '本次基本盘', comparison: '与此前对比', trend: '趋势',
}

export function statusLabel(status: string): string {
  return INSIGHT_STATUS[status]?.label ?? status
}

export function confidenceLabel(c: string): string {
  return CONFIDENCE[c]?.label ?? c
}

export function relativeTime(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Date.now() - t
  const m = Math.round(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} 小时前`
  const d = Math.round(h / 24)
  return `${d} 天前`
}

/** source_ids（checkin:ID:revision:N）→ 人可读的追溯链文本 */
export function sourceRefText(src: string): string {
  const m = /^checkin:(\d+):revision:(\d+)$/.exec(src)
  if (!m) return src
  return `打卡 #${m[1]}${Number(m[2]) > 0 ? `（修订 ${m[2]}）` : ''}`
}
