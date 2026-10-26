// API 客户端：错误统一为 ApiError（status + 人可读 message + details 列表）
import type {
  ApproachRevision, ApproachView, Checkin, Consultation, DayNutrition, ExerciseDetail,
  ExerciseRecords, ExerciseSession, ExerciseState, ExerciseSummary, ExpertInsight,
  ExpertInsightSummary, ExpertOverview, ExpertSettings, ExpertTask, FoodItem,
  MealType, NutritionReference, NutritionSummaryBlock, NutritionTargets,
  NutritionTrendDay, PlanOp, ProgressionResult, TrialObservation, TrialReview,
  BodyMeasurement, BodySummary, BodyTrend, CarePlan, EquipmentItem, LocationsResponse,
  PlanResponse, PlanRevision, PeriodSummary, Profile, Proposal, Recipe, RecoveryBrief,
  RecoveryCheckin, RecoverySummary, SubstituteResult, SymptomEpisode, TodayBrief,
  TriageResult, TrainingCalendar, TrainingLocation, TrainingTemplate,
  TrainingRestriction, Trial,
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

const put = <T>(path: string, body: unknown) =>
  req<T>(path, { method: 'PUT', body: JSON.stringify(body) })

const patch = <T>(path: string, body: unknown) =>
  req<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

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

  checkins: (uid: string, limit = 20, date?: string, offset = 0) =>
    req<{ checkins: Checkin[] }>(
      `/users/${uid}/checkins?limit=${limit}${date ? `&date=${date}` : ''}&offset=${offset}`),
  saveCheckin: (uid: string, type: string, data: unknown, submissionId?: string) =>
    post<{ id: number; type: string; warnings: string[]; existing?: boolean }>(
      `/users/${uid}/checkins`,
      { type, data, ...(submissionId ? { submission_id: submissionId } : {}) }),
  correctCheckin: (uid: string, checkinId: number,
                   payload: { expected_revision: number; data: unknown; reason: string; evidence: string }) =>
    post<Checkin>(`/users/${uid}/checkins/${checkinId}/correct`, payload),

  exercises: (params: {
    q?: string; muscle?: string; status?: string; uid?: string
    equipment?: string; pattern?: string; location?: string
    location_id?: number; available?: boolean; frequent?: boolean
  } = {}) => {
    const qs = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === '' || value === false) continue
      qs.set(key, String(value))
    }
    return req<{ count: number; exercises: ExerciseSummary[] }>(
      `/exercises${qs.size ? `?${qs}` : ''}`)
  },
  exerciseDetail: (id: string) => req<ExerciseDetail>(`/exercises/${id}`),
  exerciseStates: (uid: string) =>
    req<{ states: ExerciseState[] }>(`/users/${uid}/exercise-states`),
  locations: (uid: string) => req<LocationsResponse>(`/users/${uid}/locations`),
  createLocation: (uid: string, payload: {
    name: string; kind: TrainingLocation['kind']
    required_equipment: string[]; optional_equipment: string[]
  }) => post<{ location: TrainingLocation }>(`/users/${uid}/locations`, payload),
  updateLocation: (uid: string, locationId: number, payload: {
    name?: string; kind?: TrainingLocation['kind']
    required_equipment?: string[]; optional_equipment?: string[]
  }) => patch<{ location: TrainingLocation }>(`/users/${uid}/locations/${locationId}`, payload),
  selectLocation: (uid: string, locationId: number) =>
    post<{ location: TrainingLocation }>(`/users/${uid}/locations/${locationId}/select`, {}),
  deleteLocation: (uid: string, locationId: number) =>
    req<{ deleted: number }>(`/users/${uid}/locations/${locationId}`, { method: 'DELETE' }),
  createEquipment: (uid: string, payload: {
    name: string; category: string; aliases?: string[]; fulfills?: string | null }) =>
    post<{ equipment: EquipmentItem }>(`/users/${uid}/equipment`, payload),
  updateEquipment: (uid: string, equipmentId: string,
                    payload: Partial<EquipmentItem>) =>
    patch<{ equipment: EquipmentItem }>(`/users/${uid}/equipment/${equipmentId}`, payload),
  deleteEquipment: (uid: string, equipmentId: string) =>
    req<{ deleted: string }>(`/users/${uid}/equipment/${equipmentId}`, { method: 'DELETE' }),
  exerciseSubstitutes: (uid: string, exerciseId: string, locationId?: number) => {
    const qs = new URLSearchParams({ exercise_id: exerciseId })
    if (locationId != null) qs.set('location_id', String(locationId))
    return req<SubstituteResult>(`/users/${uid}/exercise-substitutes?${qs}`)
  },
  validateSubstitution: (uid: string, payload: {
    source_exercise_id: string; target_exercise_id: string; location_id?: number }) =>
    post<{
      source: { id: string; name: string }; target: { id: string; name: string };
      differences: string[]; safety_checked: boolean
    }>(`/users/${uid}/exercise-substitutions/validate`, payload),

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
  stageChange: (uid: string, target: string, operations: unknown[], reason: string,
                baseVersion: Record<string, unknown>) =>
    post<{ proposal_id: string; status: string; warnings: string[] }>(
      `/users/${uid}/changes/ai`, { target, operations, reason, base_version: baseVersion }),
  confirmChange: (uid: string, proposalId: string, message: string) =>
    post<{ proposal_id: string; status: string; decision?: string; note?: string }>(
      `/users/${uid}/changes/${proposalId}/confirm`, { message }),

  trials: (uid: string) => req<{ trials: Trial[] }>(`/users/${uid}/trials`),
  startTrial: (uid: string, payload: { change_desc: string; reason: string;
    observe: string; stop_rule: string; review_days?: number; baseline?: string }) =>
    post<{ trial_id: number; status: string }>(`/users/${uid}/trials`, payload),
  endTrial: (uid: string, trialId: number, payload: { outcome: string;
    decision: 'keep' | 'stop' | 'adjust' }) =>
    post<{ trial_id: number; decision: string }>(
      `/users/${uid}/trials/${trialId}/end`, payload),
  // ---- P5-C3：进阶候选 → 服务端构造提案 / 个人尝试闭环 ----
  adoptProgressionCandidate: (
    uid: string, exerciseId: string,
    payload: { option_id: string } & Record<string, unknown>,
  ) => post<{ proposal_id: string; status: string; note: string }>(
    `/users/${uid}/training-progression/${encodeURIComponent(exerciseId)}/adopt`,
    payload),
  startProgressionTrial: (
    uid: string, exerciseId: string,
    payload: { option_id: string; window_days?: number; min_sessions?: number
               } & Record<string, unknown>,
  ) => post<{ trial: Trial; observation: TrialObservation; note: string }>(
    `/users/${uid}/training-progression/${encodeURIComponent(exerciseId)}/trial`,
    payload),
  trialDetail: (uid: string, trialId: number, review = false) =>
    req<{ trial: Trial; observation: TrialObservation;
          review?: TrialReview }>(
      `/users/${uid}/trials/${trialId}${review ? '?review=1' : ''}`),
  // P6：跨专家协作
  requestCollaboration: (uid: string, scenario: string,
                         extra: { exercise_id?: string;
                                  window_days?: number } = {}) =>
    post<{ task: ExpertTask; insight: ExpertInsight | null; error?: string }>(
      `/users/${uid}/collaboration/analysis`, { scenario, ...extra }),
  collaborationDecision: (uid: string, insightId: string,
                          decision: 'ignore' | 'observe' | 'propose',
                          optionId?: string) =>
    post<{ decision: string; status?: string; proposal_id?: string;
           note: string }>(
      `/users/${uid}/collaboration/${insightId}/decision`,
      { decision, ...(optionId ? { option_id: optionId } : {}) }),
  trialDecision: (uid: string, trialId: number,
                  payload: { decision: 'keep' | 'adjust' | 'stop' | 'observe';
                             note?: string }) =>
    post<{ trial: Trial; status: string; note: string }>(
      `/users/${uid}/trials/${trialId}/decision`, payload),
  approachRevision: (uid: string, revision: number) =>
    req<{ revision: number; content: ApproachView['approach'];
          created_at: string; initiator: string }>(
      `/users/${uid}/approach/revisions/${revision}`),

  motionAnalyses: (uid: string, exerciseId?: string) => {
    const q = exerciseId ? `?exercise_id=${encodeURIComponent(exerciseId)}` : ''
    return req<{ analyses: unknown[] }>(`/users/${uid}/motion-analyses${q}`)
  },
  motionCompare: (uid: string, a: number, b: number) =>
    req<unknown>(`/users/${uid}/motion-analyses/compare?a=${a}&b=${b}`),

  // M6.4-A：训练模板（可复用，与计划/会话独立）
  trainingTemplates: (uid: string) =>
    req<{ templates: TrainingTemplate[] }>(`/users/${uid}/training-templates`),
  saveTrainingTemplate: (uid: string, payload: { id?: number; name: string;
    entries: unknown[]; hiit?: TrainingTemplate['hiit'];
    hiit_index?: number; note?: string }) =>
    post<{ id: number; name: string }>(`/users/${uid}/training-templates`, payload),
  deleteTrainingTemplate: (uid: string, templateId: number) =>
    req<{ deleted: number }>(`/users/${uid}/training-templates/${templateId}`,
                             { method: 'DELETE' }),

  // M6.3 训练数据分析（逐组口径）
  exerciseStats: (uid: string, exerciseId: string) =>
    req<{ sessions: ExerciseSession[]; records: ExerciseRecords }>(
      `/users/${uid}/exercise-stats/${encodeURIComponent(exerciseId)}`),
  trainingCalendar: (uid: string, year: number, month: number) =>
    req<TrainingCalendar>(`/users/${uid}/training-calendar?year=${year}&month=${month}`),
  periodSummary: (uid: string, days: number) =>
    req<PeriodSummary>(`/users/${uid}/period-summary?days=${days}`),

  mediaSign: (uid: string, name: string) =>
    req<{ sig: string; exp: number; ttl: number }>(
      `/users/${uid}/media-sign?name=${encodeURIComponent(name)}`),

  knowledgeSearch: (uid: string, q: string) =>
    req<unknown>(`/knowledge/search?uid=${encodeURIComponent(uid)}&q=${encodeURIComponent(q)}`),
  knowledgeImport: (uid: string, payload: { title: string; kind: string; content: string }) =>
    post<{ source_id: number; chunks: number; claims: number;
           stats: Record<string, number> }>(`/users/${uid}/knowledge/imports`, payload),
  knowledgeSources: (uid: string) =>
    req<{ sources: unknown[] }>(`/users/${uid}/knowledge/imports`),
  knowledgeClaims: (uid: string) =>
    req<{ claims: unknown[] }>(`/users/${uid}/knowledge/claims`),
  knowledgeReview: (uid: string, claimId: number, decision: 'approve' | 'reject') =>
    post<{ id: number; status: string }>(
      `/users/${uid}/knowledge/claims/${claimId}/review`, { decision }),

  consultations: (uid: string, limit = 5) =>
    req<{ consultations: Consultation[] }>(`/users/${uid}/consultations?limit=${limit}`),
  planRevisions: (uid: string) =>
    req<{ revisions: PlanRevision[] }>(`/users/${uid}/plan/revisions`),
  restorePlanVersion: (uid: string, version: number, reason: string) =>
    post<{ plan_id: number; plan_version: number; restored_from: number }>(
      `/users/${uid}/plan/revisions/${version}/restore`, { reason }),
  // P5-C2：下一次训练确定性候选（只读；每次打开都重新拉取，不依赖缓存）
  trainingProgression: (
    uid: string, exerciseId: string,
    ctx?: { planId?: number | null; planVersion?: number | null;
            plannedDay?: string | null; index?: number | null;
            plannedExerciseId?: string | null },
  ) => {
    const qs = new URLSearchParams()
    if (ctx?.planId != null) qs.set('plan_id', String(ctx.planId))
    if (ctx?.planVersion != null) qs.set('plan_version', String(ctx.planVersion))
    if (ctx?.plannedDay) qs.set('planned_day', ctx.plannedDay)
    if (ctx?.index != null) qs.set('index', String(ctx.index))
    if (ctx?.plannedExerciseId) qs.set('planned_exercise_id', ctx.plannedExerciseId)
    return req<ProgressionResult>(
      `/users/${uid}/training-progression/${encodeURIComponent(exerciseId)}${qs.size ? `?${qs}` : ''}`)
  },
  chat: (uid: string, message: string) =>
    post<{ user_id: string; reply: string }>(`/users/${uid}/chat`, { message }),

  // ---- P0 专家平台 ----
  expertsOverview: (uid: string) =>
    req<ExpertOverview>(`/users/${uid}/experts/overview`),
  expertSettings: (uid: string) =>
    req<ExpertSettings>(`/users/${uid}/experts/settings`),
  saveExpertSettings: (uid: string, payload: ExpertSettings) =>
    post<ExpertSettings>(`/users/${uid}/experts/settings`, payload),
  requestAnalysis: (uid: string, specialist: string, params: Record<string, unknown>,
                    taskType?: string) =>
    post<{ task: ExpertTask; insight: ExpertInsight | null; error?: string }>(
      `/users/${uid}/experts/analysis`,
      { specialist, params, ...(taskType ? { task_type: taskType } : {}) }),
  expertTasks: (uid: string, opts: { specialist?: string; status?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(opts).filter(([, v]) => v) as [string, string][])
    return req<{ tasks: ExpertTask[] }>(
      `/users/${uid}/experts/tasks${qs.size ? `?${qs}` : ''}`)
  },
  cancelExpertTask: (uid: string, taskId: string) =>
    post<{ task_id: string; status: string }>(
      `/users/${uid}/experts/tasks/${taskId}/cancel`, {}),
  expertInsights: (uid: string, opts: { specialist?: string; status?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams()
    if (opts.specialist) qs.set('specialist', opts.specialist)
    if (opts.status) qs.set('status', opts.status)
    if (opts.limit) qs.set('limit', String(opts.limit))
    return req<{ insights: ExpertInsightSummary[] }>(
      `/users/${uid}/expert-insights${qs.size ? `?${qs}` : ''}`)
  },
  expertInsight: (uid: string, insightId: string) =>
    req<ExpertInsight>(`/users/${uid}/expert-insights/${insightId}`),
  markInsightViewed: (uid: string, insightId: string) =>
    post<ExpertInsight>(`/users/${uid}/expert-insights/${insightId}/view`, {}),
  dismissInsight: (uid: string, insightId: string) =>
    post<ExpertInsight>(`/users/${uid}/expert-insights/${insightId}/dismiss`, {}),
  regenerateInsight: (uid: string, insightId: string) =>
    post<{ task: ExpertTask; insight: ExpertInsight | null }>(
      `/users/${uid}/expert-insights/${insightId}/regenerate`, {}),
  stageInsightProposal: (uid: string, insightId: string, optionId: string) =>
    post<{ proposal: { proposal_id: string; status: string }; note: string }>(
      `/users/${uid}/expert-insights/${insightId}/options/${optionId}/proposal`, {}),

  // ---- P1 营养系统 ----
  foods: (uid: string, opts: { q?: string; category?: string; scope?: string } = {}) => {
    const qs = new URLSearchParams({ uid, ...Object.fromEntries(
      Object.entries(opts).filter(([, v]) => v) as [string, string][]) })
    return req<{ count: number; categories: Record<string, string>; foods: FoodItem[] }>(
      `/nutrition/foods?${qs}`)
  },
  foodDetail: (foodId: string, uid: string) =>
    req<FoodItem>(`/nutrition/foods/${encodeURIComponent(foodId)}?uid=${encodeURIComponent(uid)}`),
  addFood: (uid: string, payload: Partial<FoodItem>) =>
    post<{ food_id: string; food: FoodItem }>(`/users/${uid}/nutrition/foods`, payload),
  dayNutrition: (uid: string, date: string) =>
    req<DayNutrition>(`/users/${uid}/nutrition/summary?date=${date}`),
  saveMeal: (uid: string, payload: { date: string; meal_type: MealType
                                     items: { food_id: string; amount: number; unit: string }[]
                                     notes?: string }) =>
    post<{ meal_id: number; summary: NutritionSummaryBlock }>(`/users/${uid}/meals`, payload),
  updateMeal: (uid: string, mealId: number, payload: {
    items: { food_id: string; amount: number; unit: string }[]; notes?: string
    meal_type?: MealType }) =>
    put<{ meal_id: number; summary: NutritionSummaryBlock }>(
      `/users/${uid}/meals/${mealId}`, payload),
  deleteMeal: (uid: string, mealId: number) =>
    req<{ deleted: number }>(`/users/${uid}/meals/${mealId}`, { method: 'DELETE' }),
  copyDayMeals: (uid: string, fromDate: string, toDate: string) =>
    post<{ copied: number }>(`/users/${uid}/meals/copy-day`,
                              { from_date: fromDate, to_date: toDate }),
  nutritionTrends: (uid: string, days: number) =>
    req<{ days_window: number; days: NutritionTrendDay[]; note: string }>(
      `/users/${uid}/nutrition/trends?days=${days}`),
  setDayComplete: (uid: string, date: string, complete: boolean) =>
    post<{ date: string; complete: boolean }>(
      `/users/${uid}/nutrition/days/${date}/complete`, { complete }),
  nutritionTargets: (uid: string) =>
    req<{ targets: NutritionTargets; reference: NutritionReference }>(
      `/users/${uid}/nutrition/targets`),
  saveNutritionTargets: (uid: string, payload: Partial<NutritionTargets>) =>
    post<{ targets: NutritionTargets }>(`/users/${uid}/nutrition/targets`, payload),
  frequentFoods: (uid: string) =>
    req<{ foods: { food_id: string; food_name: string; count: number
                   last_unit?: string; last_amount?: number
                   serving_units?: import('./types').ServingUnit[] }[] }>(
      `/users/${uid}/nutrition/frequent`),
  recipes: (uid: string) => req<{ recipes: Recipe[] }>(`/users/${uid}/nutrition/recipes`),
  saveRecipe: (uid: string, payload: { name: string
    items: { food_id: string; amount: number; unit: string }[]; id?: number }) =>
    post<{ recipe_id: number }>(`/users/${uid}/nutrition/recipes`, payload),
  deleteRecipe: (uid: string, recipeId: number) =>
    req<{ deleted: number }>(`/users/${uid}/nutrition/recipes/${recipeId}`,
                              { method: 'DELETE' }),

  // ---- P2 身体数据与恢复管理 ----
  bodyMeasurements: (uid: string, opts: { start?: string; end?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(opts).filter(([, v]) => v) as [string, string][])
    return req<{ measurements: BodyMeasurement[] }>(
      `/users/${uid}/body-measurements${qs.size ? `?${qs}` : ''}`)
  },
  addBodyMeasurement: (uid: string, data: Record<string, unknown>, submissionId?: string) =>
    post<{ measurement_id: number; existing: boolean; measurement: BodyMeasurement }>(
      `/users/${uid}/body-measurements`,
      { data, ...(submissionId ? { submission_id: submissionId } : {}) }),
  updateBodyMeasurement: (uid: string, mid: number, payload: {
    expected_revision: number; data: Record<string, unknown>
    reason: string; evidence: string }) =>
    patch<BodyMeasurement>(`/users/${uid}/body-measurements/${mid}`, payload),
  deleteBodyMeasurement: (uid: string, mid: number) =>
    req<{ deleted: number }>(`/users/${uid}/body-measurements/${mid}`,
                              { method: 'DELETE' }),
  bodyMeasurementRevisions: (uid: string, mid: number) =>
    req<{ revisions: { revision: number; reason: string; evidence: string
                       created_at: string }[] }>(
      `/users/${uid}/body-measurements/${mid}/revisions`),
  bodySummary: (uid: string, days = 30) =>
    req<BodySummary>(`/users/${uid}/body-summary?days=${days}`),
  bodyTrend: (uid: string, metric: string, days: number) =>
    req<BodyTrend>(`/users/${uid}/body-trend?metric=${metric}&days=${days}`),

  deleteMotionAnalysis: (uid: string, analysisId: number) =>
    req<{ deleted: number }>(`/users/${uid}/motion-analyses/${analysisId}`,
                              { method: 'DELETE' }),
  motionNotes: (uid: string, analysisId: number, notes: string) =>
    post<{ analysis_id: number; user_notes: string }>(
      `/users/${uid}/motion-analyses/${analysisId}/notes`, { notes }),

  recoveryCheckins: (uid: string, days = 90) =>
    req<{ checkins: RecoveryCheckin[] }>(`/users/${uid}/recovery-checkins?days=${days}`),
  saveRecoveryCheckin: (uid: string, data: Record<string, unknown>, submissionId?: string) =>
    post<{ recovery_id: number; revision: number; created: boolean; existing?: boolean }>(
      `/users/${uid}/recovery-checkins`,
      { data, ...(submissionId ? { submission_id: submissionId } : {}) }),
  deleteRecoveryCheckin: (uid: string, rid: number) =>
    req<{ deleted: number }>(`/users/${uid}/recovery-checkins/${rid}`,
                              { method: 'DELETE' }),
  recoverySummary: (uid: string, days = 14) =>
    req<RecoverySummary>(`/users/${uid}/recovery-summary?days=${days}`),
  recoveryBrief: (uid: string) =>
    req<RecoveryBrief>(`/users/${uid}/pre-training-recovery-brief`),

  // ---- P3 康复辅助 ----
  symptomEpisodes: (uid: string, status?: string) =>
    req<{ episodes: SymptomEpisode[] }>(
      `/users/${uid}/symptom-episodes${status ? `?status=${status}` : ''}`),
  symptomEpisode: (uid: string, eid: number) =>
    req<SymptomEpisode & { observations: SymptomEpisode['observations'] }>(
      `/users/${uid}/symptom-episodes/${eid}`),
  reportSymptom: (uid: string, data: Record<string, unknown>, submissionId?: string) =>
    post<{ episode_id: number; triage: TriageResult; restriction_id: number | null }>(
      `/users/${uid}/symptom-episodes`,
      { data, ...(submissionId ? { submission_id: submissionId } : {}) }),
  observeSymptom: (uid: string, eid: number, data: Record<string, unknown>) =>
    post<{ observation_id: number; triage: TriageResult }>(
      `/users/${uid}/symptom-episodes/${eid}/observations`, { data }),
  triagePreview: (data: Record<string, unknown>) =>
    post<TriageResult>('/rehab/triage-preview', data),
  restrictions: (uid: string, status?: string) =>
    req<{ restrictions: TrainingRestriction[] }>(
      `/users/${uid}/training-restrictions${status ? `?status=${status}` : ''}`),
  liftRestriction: (uid: string, rid: number, payload: {
    expected_revision: number; lift_evidence: string; reason?: string }) =>
    post<TrainingRestriction>(`/users/${uid}/training-restrictions/${rid}/lift`, payload),
  carePlans: (uid: string) => req<{ plans: CarePlan[] }>(`/users/${uid}/care-plans`),
  createCarePlan: (uid: string, payload: Record<string, unknown>) =>
    post<{ plan_id: number }>(`/users/${uid}/care-plans`, payload),
  logCareActivity: (uid: string, aid: number, payload: {
    local_date: string; completed: boolean; feedback?: string }) =>
    post<{ log_id: number }>(`/users/${uid}/care-activities/${aid}/log`, payload),
}
