// API 客户端：错误统一为 ApiError（status + 人可读 message + details 列表）
import type {
  ApproachRevision, ApproachView, Checkin, Consultation, ExerciseDetail,
  ExerciseState, ExerciseSummary, PlanOp, PlanResponse, PlanRevision, Profile,
  Proposal, TodayBrief, Trial,
} from './types'

export class ApiError extends Error {
  status: number
  details: string[]
  constructor(status: number, message: string, details: string[] = []) {
    super(message)
    this.status = status
    this.details = details
  }
}

function accessToken(): string {
  try { return localStorage.getItem('fc-access-token') || '' } catch { return '' }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken() ? { 'X-Access-Token': accessToken() } : {}),
        ...(init?.headers as Record<string, string> | undefined),
      },
    })
  } catch {
    throw new ApiError(0, '网络不可用')
  }
  if (!res.ok) {
    let detail: { error?: string; details?: string[] } | string | undefined
    try { detail = (await res.json()).detail } catch { /* 非 JSON 错误体 */ }
    const msg = typeof detail === 'string' ? detail
      : detail?.error || `请求失败（${res.status}）`
    throw new ApiError(res.status, msg, typeof detail === 'object' ? detail?.details || [] : [])
  }
  return res.json() as Promise<T>
}

const post = <T>(path: string, body: unknown) =>
  req<T>(path, { method: 'POST', body: JSON.stringify(body) })

export interface OnboardingPayload {
  basic: { age: number; gender: string; height_cm: number; weight_kg: number }
  goal: { primary: string }
  experience?: { training_years?: number; recent_layoff_weeks?: number }
  resources: { location: string; days_per_week: number; session_minutes: number }
  conditions: {
    injuries: string[]
    injuries_evidence: string
    health_screen: Record<string, string>
    health_screen_evidence: string
  }
}

export interface OnboardingResult {
  plan_id: number
  version: number
  medical_status: string
  suspended: boolean
  level: string
  text: string
}

export const api = {
  health: () => req<{ status: string; exercises: number }>('/health'),
  profile: (uid: string) =>
    req<{ user_id: string; profile: Profile; summary: string; plan_fenced: boolean }>(
      `/users/${uid}/profile`),
  today: (uid: string) => req<TodayBrief>(`/users/${uid}/today`),
  onboard: (uid: string, payload: OnboardingPayload) =>
    post<OnboardingResult>(`/users/${uid}/onboarding`, payload),

  plan: (uid: string) => req<PlanResponse>(`/users/${uid}/plan`),

  // M1.1 补充：计划本地缓存（断网时训练执行降级用，避免"离线就不能练"）
  cachePlan(uid: string, plan: PlanResponse) {
    try { localStorage.setItem(`fc-plan-${uid}`, JSON.stringify(plan)) } catch { /* 存储不可用 */ }
  },
  cachedPlan(uid: string): PlanResponse | null {
    try {
      const raw = localStorage.getItem(`fc-plan-${uid}`)
      return raw ? JSON.parse(raw) as PlanResponse : null
    } catch { return null }
  },
  planEdits: (uid: string, operations: PlanOp[], reason: string,
              baseVersion?: Record<string, unknown>) =>
    post<{ plan_id: number; plan_version: number; changes: string[]; warnings: string[] }>(
      `/users/${uid}/plan/edits`, { operations, reason, base_version: baseVersion }),

  checkins: (uid: string, limit = 20) =>
    req<{ checkins: Checkin[] }>(`/users/${uid}/checkins?limit=${limit}`),
  saveCheckin: (uid: string, type: string, data: unknown, submissionId?: string) =>
    post<{ id: number; type: string; warnings: string[]; existing?: boolean }>(
      `/users/${uid}/checkins`,
      { type, data, ...(submissionId ? { submission_id: submissionId } : {}) }),
  correctCheckin: (uid: string, checkinId: number,
                   payload: { expected_revision: number; data: unknown; reason: string; evidence: string }) =>
    post<Checkin>(`/users/${uid}/checkins/${checkinId}/correct`, payload),

  exercises: (params: { q?: string; muscle?: string; status?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][])
    return req<{ count: number; exercises: ExerciseSummary[] }>(
      `/exercises${qs.size ? `?${qs}` : ''}`)
  },
  exerciseDetail: (id: string) => req<ExerciseDetail>(`/exercises/${id}`),
  exerciseStates: (uid: string) =>
    req<{ states: ExerciseState[] }>(`/users/${uid}/exercise-states`),

  approach: (uid: string) => req<ApproachView>(`/users/${uid}/approach`),
  initApproach: (uid: string) => post<ApproachView>(`/users/${uid}/approach/initialize`, {}),
  revisions: (uid: string) =>
    req<{ revisions: ApproachRevision[] }>(`/users/${uid}/approach/revisions`),
  restoreRevision: (uid: string, revision: number, reason: string) =>
    post<{ restored_from: number }>(
      `/users/${uid}/approach/revisions/${revision}/restore`, { reason }),

  submitChange: <T extends Record<string, unknown>>(uid: string, target: string,
                   operations: unknown[], reason: string, baseVersion: Record<string, unknown>) =>
    post<T>(`/users/${uid}/changes`,
            { target, operations, reason, base_version: baseVersion }),

  changes: (uid: string, status?: string) =>
    req<{ proposals: Proposal[] }>(
      `/users/${uid}/changes${status ? `?status=${status}` : ''}`),
  confirmChange: (uid: string, proposalId: string, message: string) =>
    post<{ proposal_id: string; status: string; decision?: string; note?: string }>(
      `/users/${uid}/changes/${proposalId}/confirm`, { message }),

  trials: (uid: string) => req<{ trials: Trial[] }>(`/users/${uid}/trials`),

  consultations: (uid: string, limit = 5) =>
    req<{ consultations: Consultation[] }>(`/users/${uid}/consultations?limit=${limit}`),
  planRevisions: (uid: string) =>
    req<{ revisions: PlanRevision[] }>(`/users/${uid}/plan/revisions`),
  restorePlanVersion: (uid: string, version: number, reason: string) =>
    post<{ plan_id: number; plan_version: number; restored_from: number }>(
      `/users/${uid}/plan/revisions/${version}/restore`, { reason }),
  chat: (uid: string, message: string) =>
    post<{ user_id: string; reply: string }>(`/users/${uid}/chat`, { message }),
}
