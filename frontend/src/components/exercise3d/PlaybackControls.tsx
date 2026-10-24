// M6.4-B B2.4：三维播放控制条（播放/暂停、循环、0.25×–2×、拖动进度、阶段提示）。
import { Pause, Play, Repeat, Repeat1 } from 'lucide-react'

export interface TeachingPhase {
  key: string
  label: string
  t: [number, number]
}

const SPEEDS = [0.25, 0.5, 1, 2] as const

export function PlaybackControls({ playing, time, duration, loop, speed, phase,
                                  onToggle, onSeek, onToggleLoop, onSpeed }: {
  playing: boolean
  time: number
  duration: number
  loop: boolean
  speed: number
  phase: TeachingPhase | null
  onToggle: () => void
  onSeek: (t: number) => void
  onToggleLoop: () => void
  onSpeed: (s: number) => void
}) {
  const fmt = (t: number) => `${t.toFixed(1)}s`
  return (
    <div className="border-t border-line bg-surface/95 px-3 pb-3 pt-2.5 backdrop-blur">
      <div className="flex items-center gap-2.5">
        <button aria-label={playing ? '暂停' : '播放'}
                onClick={onToggle}
                className="flex size-10 shrink-0 items-center justify-center rounded-full
                           bg-night text-white transition-transform active:scale-95">
          {playing ? <Pause size={17} /> : <Play size={17} className="ml-0.5" />}
        </button>
        <input type="range" min={0} max={duration} step={0.02} value={time}
               aria-label="动画进度"
               onChange={(e) => onSeek(Number(e.target.value))}
               className="h-1.5 min-w-0 flex-1 cursor-pointer accent-lime-600" />
        <span className="nums shrink-0 text-xs text-muted">
          {fmt(time)} / {fmt(duration)}
        </span>
        <button aria-label={loop ? '循环播放' : '单次播放'} title={loop ? '循环播放' : '单次播放'}
                onClick={onToggleLoop}
                className={`flex size-9 shrink-0 items-center justify-center rounded-full
                            transition-colors ${loop ? 'text-accent-deep' : 'text-faint'} hover:bg-ink/5`}>
          {loop ? <Repeat size={16} /> : <Repeat1 size={16} />}
        </button>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div className="flex gap-1 rounded-lg bg-ink/5 p-0.5">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => onSpeed(s)}
                    className={`nums rounded-md px-2 py-1 text-[11px] font-medium
                                transition-colors ${speed === s
                      ? 'bg-surface text-ink shadow-card'
                      : 'text-muted hover:text-ink'}`}>
              {s}×
            </button>
          ))}
        </div>
        {phase && (
          <span className="tag ml-auto max-w-full truncate bg-accent-soft text-accent-deep"
                title="阶段提示为教学说明，不构成个人动作判定">
            {phase.label}
          </span>
        )}
      </div>
    </div>
  )
}
