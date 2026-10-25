// 康复展示工具（与后端口径一致）
export const TRIAGE_TONE: Record<string, { label: string; cls: string }> = {
  urgent_evaluation: { label: '建议尽快就医评估', cls: 'bg-red-50 text-red-700 border-red-300' },
  professional_evaluation: { label: '建议专业评估', cls: 'bg-amber-50 text-amber-800 border-amber-300' },
  uncertain: { label: '信息不足，保守处理', cls: 'bg-amber-50/70 text-amber-700 border-amber-200' },
  general_information: { label: '一般情况说明', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200' },
}

export const REGION_LABEL: Record<string, string> = {
  knee: '膝', shoulder: '肩', elbow: '肘', wrist: '腕', lower_back: '腰背',
  hip: '髋', ankle: '踝', neck: '颈', other: '其他',
}

export const SIDE_LABEL: Record<string, string> = {
  left: '左', right: '右', bilateral: '双侧',
}

export const SOURCE_LABEL: Record<string, string> = {
  user_reported: '用户自行报告', professional: '专业人员给出',
  triage_recommended: '安全分流提示（待确认）',
}

export function regionText(region: string, side: string | null): string {
  return `${REGION_LABEL[region] ?? region}${side ? `（${SIDE_LABEL[side] ?? side}）` : ''}`
}
