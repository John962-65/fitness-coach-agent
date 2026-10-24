// 客户端状态：当前用户、训练执行会话（刷新不丢）、休息计时、离线队列计数。
// 持久化用显式 localStorage 读写（zustand persist 中间件与严格 TS 的泛型
// 推断在重现问题，显式化反而更简单可靠）。
import { create } from 'zustand'

export interface LoggedSet {
  weight: number | null
  reps: number | null
  rpe: number | null
  warmup: boolean
}

export interface SessionEntry {
  exercise_id: string
  name: string
  target: { sets: number | string; reps: number | string; weight: number | null }
  note?: string
  logged: LoggedSet[]
  replaced_with?: string // 训练中临时替换（只影响本次记录，不改计划）
}

export interface WorkoutSession {
  day: string
  date: string
  entries: SessionEntry[]
  started_at: string
  notes: string
}

export interface Settings {
  restSeconds: number
}

interface AppState {
  uid: string
  setUid: (uid: string) => void

  session: WorkoutSession | null
  startSession: (day: string, entries: SessionEntry[]) => void
  logSet: (entryIdx: number, s: LoggedSet) => void
  removeLastSet: (entryIdx: number) => void
  replaceExercise: (entryIdx: number, newName: string) => void
  setSessionNotes: (notes: string) => void
  clearSession: () => void

  restEndsAt: number | null
  startRest: () => void
  stopRest: () => void

  settings: Settings
  setRestSeconds: (n: number) => void

  offlineCount: number
  setOfflineCount: (n: number) => void
}

const STORAGE_KEY = 'fc-app-v1'
const PERSISTED_KEYS = ('uid session settings offlineCount').split(' ')

const today = () => new Date().toISOString().slice(0, 10)

function loadPersisted(): Partial<AppState> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, unknown>
    const out: Record<string, unknown> = {}
    for (const key of PERSISTED_KEYS) {
      if (key in parsed) out[key] = parsed[key]
    }
    return out as Partial<AppState>
  } catch {
    return {}
  }
}

export const useApp = create<AppState>()((set) => ({
  uid: '',
  setUid: (uid) => set({ uid, session: null }),

  session: null,
  startSession: (day, entries) =>
    set({ session: { day, date: today(), entries, started_at: new Date().toISOString(), notes: '' } }),
  logSet: (entryIdx, s) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, logged: [...e.logged, s] } : e) }
        : st.session,
    })),
  removeLastSet: (entryIdx) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, logged: e.logged.slice(0, -1) } : e) }
        : st.session,
    })),
  replaceExercise: (entryIdx, newName) =>
    set((st) => ({
      session: st.session
        ? { ...st.session, entries: st.session.entries.map((e, i) =>
            i === entryIdx ? { ...e, replaced_with: newName } : e) }
        : st.session,
    })),
  setSessionNotes: (notes) =>
    set((st) => (st.session ? { session: { ...st.session, notes } } : st)),
  clearSession: () => set({ session: null }),

  restEndsAt: null,
  startRest: () => set({ restEndsAt: Date.now() + useApp.getState().settings.restSeconds * 1000 }),
  stopRest: () => set({ restEndsAt: null }),

  settings: { restSeconds: 90 },
  setRestSeconds: (n: number) => set({ settings: { restSeconds: n } }),

  offlineCount: 0,
  setOfflineCount: (n: number) => set({ offlineCount: n }),

  ...loadPersisted(),
}))

// 每次状态变化后把需要跨会话保留的部分写回 localStorage
useApp.subscribe((state) => {
  try {
    const slim: Record<string, unknown> = {}
    for (const key of PERSISTED_KEYS) slim[key] = (state as unknown as Record<string, unknown>)[key]
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  } catch { /* 隐私模式等场景下持久化不可用，不影响功能 */ }
})
