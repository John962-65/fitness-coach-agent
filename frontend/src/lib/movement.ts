// 动作技术工作台展示工具（与后端口径一致）
export const DEMO_FIVE = [
  { id: 'barbell_back_squat', name: '杠铃深蹲' },
  { id: 'barbell_bench_press', name: '杠铃卧推' },
  { id: 'deadlift', name: '硬拉' },
  { id: 'barbell_row', name: '杠铃划船' },
  { id: 'dumbbell_shoulder_press', name: '哑铃肩推' },
] as const

export const QUALITY_TONE: Record<string, { label: string; cls: string }> = {
  usable: { label: '可用', cls: 'bg-emerald-50 text-emerald-700' },
  poor: { label: '质量不足', cls: 'bg-amber-50 text-amber-700' },
  unsupported: { label: '不支持的动作', cls: 'bg-red-50 text-red-600' },
  unknown: { label: '未知', cls: 'bg-ink/5 text-muted' },
}

export const OBS_KIND: Record<string, string> = {
  'view-limitation': '视角限制', 'rep-count': '周期计数', rhythm: '节奏',
  consistency: '周期一致性', 'fault-observation': '可见几何提示',
  insufficient: '观察不足',
}

export const STATUS_ZH: Record<string, string> = {
  processing: '分析中', ready: '完成', failed: '失败',
  draft: '草稿', reviewed: '已审核', approved: '已批准', incomplete: '不完整',
}

export interface TechProfile {
  model_version: string
  video_quality: { status: string; view: string; detection_ratio?: number
                   valid_ratio?: number; limitations: string[] }
  motion_observations: { kind: string; text: string }[]
  phase_timestamps: { rep: number; start_s: number; end_s: number; peak_s: number }[]
  review_status: string
  user_notes?: string | null
}

export function viewCompatible(a: TechProfile | null, b: TechProfile | null): boolean {
  if (!a || !b) return false
  return a.video_quality.view === b.video_quality.view
    && a.video_quality.status === 'usable' && b.video_quality.status === 'usable'
}

export function videoUrlBase(path: string): string {
  // motion_analyses.video_path 形如 .../media/{uid}/ma*.mp4 → 取文件名
  const name = path.split('/').pop() ?? ''
  return name
}
