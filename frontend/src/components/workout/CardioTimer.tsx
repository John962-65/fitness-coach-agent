import { useEffect, useState } from 'react'
import { Check, Flag, Pause, Play, Timer, Undo2 } from 'lucide-react'
import { Button, Input } from '../Bits'
import type { SessionEntry, LoggedSet } from '../../store'
import type { SessionEntryCardio } from '../../types'

export function createCardioState(now = Date.now()): SessionEntryCardio {
  return { startedAt: now, pausedAt: null, pausedTotalMs: 0, endedAt: null }
}

export function cardioElapsedSeconds(cardio: SessionEntryCardio, now = Date.now()) {
  const end = cardio.endedAt ?? cardio.pausedAt ?? now
  return Math.max(0, Math.floor((end - cardio.startedAt - cardio.pausedTotalMs) / 1000))
}

export function pauseCardio(cardio: SessionEntryCardio, now = Date.now()): SessionEntryCardio {
  if (cardio.endedAt || cardio.pausedAt) return cardio
  return { ...cardio, pausedAt: now }
}

export function resumeCardio(cardio: SessionEntryCardio, now = Date.now()): SessionEntryCardio {
  if (cardio.endedAt || !cardio.pausedAt) return cardio
  return { ...cardio,
    pausedTotalMs: cardio.pausedTotalMs + Math.max(0, now - cardio.pausedAt),
    pausedAt: null }
}

export function endCardio(cardio: SessionEntryCardio, now = Date.now()): SessionEntryCardio {
  if (cardio.endedAt) return cardio
  const pausedTotalMs = cardio.pausedTotalMs
    + (cardio.pausedAt ? Math.max(0, now - cardio.pausedAt) : 0)
  return { ...cardio, endedAt: now, pausedAt: null, pausedTotalMs }
}

export default function CardioTimer({ idx, entry, onUpdate, onLog, onUndo }: {
  idx: number
  entry: SessionEntry
  onUpdate: (patch: Partial<SessionEntry>) => void
  onLog: (idx: number, s: LoggedSet) => void
  onUndo: (idx: number) => void
}) {
  const cardio = entry.cardio
  const [now, setNow] = useState(Date.now())
  const [error, setError] = useState('')
  const logged = entry.logged.some((l) => !l.warmup)

  useEffect(() => {
    if (!cardio || cardio.endedAt || cardio.pausedAt) return
    const h = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(h)
  }, [cardio])

  if (!cardio) return null
  const running = !cardio.pausedAt && !cardio.endedAt
  const measuredSeconds = cardioElapsedSeconds(cardio, now)
  const elapsedSec = cardio.elapsedOverride != null && cardio.elapsedOverride !== ''
    ? Number(cardio.elapsedOverride) : measuredSeconds
  const displaySeconds = Number.isFinite(elapsedSec) ? Math.max(0, Math.floor(elapsedSec)) : 0
  const mm = String(Math.floor(displaySeconds / 60)).padStart(2, '0')
  const ss = String(displaySeconds % 60).padStart(2, '0')

  function patch(patch: Partial<SessionEntryCardio>) {
    onUpdate({ cardio: { ...cardio!, ...patch } })
  }

  function log() {
    if (logged) return
    const seconds = Number(elapsedSec)
    const distance = cardio!.distance?.trim() ? Number(cardio!.distance) : undefined
    const rpe = cardio!.rpe?.trim() ? Number(cardio!.rpe) : undefined
    if (!Number.isFinite(seconds) || !Number.isInteger(seconds) || seconds < 1) {
      setError('实际用时需为不少于 1 秒的整数'); return
    }
    if (distance !== undefined && (!Number.isFinite(distance) || distance <= 0)) {
      setError('距离需为大于 0 的有效数字'); return
    }
    if (rpe !== undefined && (!Number.isFinite(rpe) || rpe < 1 || rpe > 10)) {
      setError('RPE 需为 1-10 的有效数字'); return
    }
    const at = new Date().toISOString()
    const result: LoggedSet = entry.measurement === 'distance_time' && distance !== undefined
      ? { type: 'distance_time', distance_m: distance, duration_seconds: seconds,
          ...(rpe !== undefined ? { rpe } : {}), warmup: false, at }
      : { type: 'duration', duration_seconds: seconds,
          ...(rpe !== undefined ? { rpe } : {}), warmup: false, at }
    onLog(idx, result)
    setError('')
  }

  return (
    <div className="border-t border-line bg-canvas/60 px-4 pb-4 pt-3">
      <div className="rounded-xl bg-night p-4 text-center text-white">
        <p className="flex items-center justify-center gap-1.5 text-2xs text-white/60">
          <Timer size={12} />
          {cardio.endedAt ? '已结束' : running ? '进行中' : '已暂停'}
        </p>
        <p className="nums mt-1 text-4xl font-bold tabular-nums">{mm}:{ss}</p>
        <p className="mt-1 text-2xs text-white/50">
          按时间戳计时，暂停时间不计入；后台经过时间如实计入，结束后可修正
        </p>
      </div>
      {!cardio.endedAt ? (
        <div className="mt-2.5 flex gap-2">
          {running ? (
            <button className="btn-soft btn flex-1"
                    onClick={() => onUpdate({ cardio: pauseCardio(cardio, Date.now()) })}>
              <Pause size={15} /> 暂停
            </button>
          ) : (
            <button className="btn-primary btn flex-1"
                    onClick={() => {
                      const resumed = resumeCardio(cardio, Date.now())
                      onUpdate({ cardio: resumed })
                      setNow(Date.now())
                    }}>
              <Play size={15} /> 恢复
            </button>
          )}
          <button className="btn-ghost btn flex-1 !text-red-600"
                  onClick={() => onUpdate({ cardio: endCardio(cardio, Date.now()) })}>
            <Flag size={15} /> 结束
          </button>
        </div>
      ) : (
        <div className="mt-2.5 space-y-2">
          {entry.measurement === 'distance_time' && (
            <label className="block">
              <span className="mb-1 block text-xs text-muted">距离（米，可选）</span>
              <Input inputMode="numeric" placeholder="如 5000" value={cardio.distance ?? ''}
                     onChange={(e) => patch({ distance: e.target.value })} />
            </label>
          )}
          <label className="block">
            <span className="mb-1 block text-xs text-muted">实际用时（秒，可手动修正）</span>
            <Input inputMode="numeric" value={String(elapsedSec)}
                   onChange={(e) => patch({ elapsedOverride: e.target.value })} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-muted">主观强度 RPE 1-10（可选）</span>
            <Input inputMode="numeric" placeholder="6" value={cardio.rpe ?? ''}
                   onChange={(e) => patch({ rpe: e.target.value })} />
          </label>
          {error && <p className="text-xs text-red-600" role="alert">{error}</p>}
          {!logged ? (
            <Button block onClick={log}>
              <Check size={15} /> 记录本次有氧
            </Button>
          ) : (
            <div className="rounded-xl bg-emerald-50 p-2.5 text-xs text-emerald-700">
              <p>已记录到本会话，随「完成训练」一起保存。</p>
              <button className="mt-1 flex items-center gap-1 underline"
                      onClick={() => onUndo(idx)}>
                <Undo2 size={13} /> 撤销重记
              </button>
            </div>
          )}
          <p className="text-2xs leading-relaxed text-faint">
            与力量动作共用保存、离线和纠错链路；不生成估算卡路里。
          </p>
        </div>
      )}
    </div>
  )
}
