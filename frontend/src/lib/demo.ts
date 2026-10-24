// M6.4-B B1.1/B4：演示模式可用性（纯函数，可测）。
// 规则：只展示已有资源对应的选项——视频入口仅当用户自己导入关联了媒体；
// 三维入口仅当公共 manifest 提供已授权模型；图文教学始终可用。
export interface TeachingPhase { key: string; label: string; t: [number, number] }

export interface Demo3D {
  model_url: string
  preview_url?: string
  animation_name: string
  duration: number
  loop: boolean
  supported_views: string[]
  teaching_phases: TeachingPhase[]
  review_status?: string
  size_bytes?: number
}

export type DemoMode = 'video' | 'model3d' | 'text'

export function demoOptions(hasUserVideo: boolean,
                             model3d: Demo3D | null | undefined): { value: DemoMode; label: string }[] {
  const opts: { value: DemoMode; label: string }[] = []
  if (hasUserVideo) opts.push({ value: 'video', label: '视频演示' })
  if (model3d && model3d.model_url) opts.push({ value: 'model3d', label: '3D 演示' })
  opts.push({ value: 'text', label: '图文教学' })
  return opts
}

export function defaultDemoMode(hasUserVideo: boolean,
                                model3d: Demo3D | null | undefined): DemoMode {
  if (model3d && model3d.model_url) return 'model3d'
  if (hasUserVideo) return 'video'
  return 'text'
}

export const TEACHING_SECTION_LABEL: Record<string, string> = {
  setup: '准备姿势', execution: '执行步骤', breathing: '呼吸与节奏',
  common_errors: '常见错误', cautions: '注意事项', conditions: '适用条件',
}

/** 教学节审核状态 → 展示文案/色调（B0.2：状态如实展示，不自动升级） */
export const TEACHING_STATUS: Record<string, { label: string; tone: 'amber' | 'green' | 'neutral' }> = {
  draft: { label: '整理稿', tone: 'amber' },
  reviewed: { label: '已审阅', tone: 'green' },
  approved: { label: '已批准', tone: 'green' },
  incomplete: { label: '资料不全', tone: 'neutral' },
}
