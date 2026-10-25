import { useState } from 'react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, Sheet, Textarea } from '../../components/Bits'
import { useApp } from '../../store'
import { RECOVERY_SCALES, SORENESS_REGIONS } from '../../lib/recovery'

/** 快速恢复打卡：全部可选（至少一项）；当天已记录则走修订（需说明原因） */
export default function RecoveryQuickCheckin({ date, hasExisting, onClose, onSaved }: {
  date: string; hasExisting: boolean; onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [sleepHours, setSleepHours] = useState('')
  const [scales, setScales] = useState<Record<string, number | null>>({
    sleep_quality: null, fatigue: null, muscle_soreness: null, training_readiness: null,
  })
  const [regions, setRegions] = useState<string[]>([])
  const [notes, setNotes] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const filled = sleepHours.trim() !== ''
    || Object.values(scales).some((v) => v != null)
    || regions.length > 0 || notes.trim() !== ''

  async function save() {
    setBusy(true); setError('')
    try {
      await api.saveRecoveryCheckin(uid, {
        local_date: date,
        ...(sleepHours.trim() !== '' ? { sleep_hours: Number(sleepHours) } : {}),
        ...Object.fromEntries(Object.entries(scales).filter(([, v]) => v != null)),
        soreness_regions: regions,
        ...(notes.trim() ? { notes } : {}),
        ...(hasExisting ? { reason: reason || '更新当日恢复记录',
                            evidence: reason || '用户在工作台更新' } : {}),
      }, `rec-${date}-${Date.now().toString(36)}`)
      onSaved(); onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open title={hasExisting ? `更新 ${date.slice(5)} 的恢复记录` : `记录 ${date.slice(5)} 的恢复状态`}
           onClose={onClose}>
      {hasExisting && (
        <p className="mb-2 rounded-xl bg-amber-50 p-2.5 text-2xs leading-relaxed text-amber-800">
          当天已有记录：再次保存会生成修订（原值留痕），请说明修改原因。
        </p>
      )}
      <label className="block">
        <span className="mb-1 block text-xs text-muted">睡眠时长（小时，可选）</span>
        <Input inputMode="decimal" value={sleepHours} onChange={(e) => setSleepHours(e.target.value)}
               placeholder="如 7.5" />
      </label>
      <div className="mt-3 space-y-3">
        {RECOVERY_SCALES.map((scale) => (
          <div key={scale.key}>
            <p className="text-xs font-medium">{scale.label}<span className="ml-1 text-2xs text-faint">1-5</span></p>
            <div className="mt-1 flex gap-1.5">
              {[1, 2, 3, 4, 5].map((v) => (
                <button key={v} type="button"
                        className={`h-9 flex-1 rounded-lg text-xs font-medium transition-colors ${
                          scales[scale.key] === v
                            ? 'bg-night text-white'
                            : 'bg-canvas text-muted hover:bg-ink/8'}`}
                        onClick={() => setScales({ ...scales,
                          [scale.key]: scales[scale.key] === v ? null : v })}>
                  {v}
                </button>
              ))}
            </div>
            <p className="mt-0.5 text-2xs text-faint">
              {scales[scale.key] != null
                ? `${scales[scale.key]} = ${scale.levels[scales[scale.key]!]}`
                : `1=${scale.levels[1]} · 5=${scale.levels[5]}`}
            </p>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <p className="text-xs font-medium">酸痛区域（可选）</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {SORENESS_REGIONS.map((r) => (
            <button key={r} type="button"
                    className={`tag ${regions.includes(r) ? 'bg-night text-white' : 'bg-ink/5 text-muted'}`}
                    onClick={() => setRegions(regions.includes(r)
                      ? regions.filter((x) => x !== r) : [...regions, r])}>
              {r}
            </button>
          ))}
        </div>
        <p className="mt-1 text-2xs leading-relaxed text-faint">
          普通训练后的酸痛在这里记录；持续/剧烈疼痛、明显功能受限等异常情况
          请优先考虑就医评估，不要只当作酸痛记分。
        </p>
      </div>
      <label className="mt-3 block">
        <span className="mb-1 block text-xs text-muted">备注（可选）</span>
        <Textarea value={notes} rows={2} onChange={(e) => setNotes(e.target.value)}
                  placeholder="如：昨晚熬夜，下午有点困" />
      </label>
      {hasExisting && (
        <label className="mt-2 block">
          <span className="mb-1 block text-xs text-muted">修改原因</span>
          <Input value={reason} onChange={(e) => setReason(e.target.value)}
                 placeholder="如：下午补充的" />
        </label>
      )}
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <Button className="mt-3" block disabled={busy || !filled} onClick={save}>
        {busy ? '保存中…' : hasExisting ? '保存修订' : '完成打卡'}
      </Button>
    </Sheet>
  )
}
