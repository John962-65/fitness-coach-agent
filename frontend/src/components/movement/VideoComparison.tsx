import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react'
import { Pause, Play } from 'lucide-react'
import { api, ApiError } from '../../api'
import { ErrorBox, Select } from '../../components/Bits'
import { useApp } from '../../store'
import type { Demo3D } from '../../types'

const Exercise3DViewer = lazy(() => import('../exercise3d/Exercise3DViewer'))

/**
 * 用户视频 × 三维教学动画分屏对照（P4-3）。
 * 原则：两侧独立播放/暂停/倍速；手动对齐阶段；对照用于观察理解，
 * 不构成"与动画重合=正确"的判定；切换三维视角不改变视频数据；
 * 卸载时清理播放器（视频暂停、GLB 由 Viewer 自行 dispose）。
 */
export default function VideoComparison({ videoPath, demo, phases }: {
  videoPath: string
  demo: Demo3D
  phases: { rep: number; start_s: number; end_s: number; peak_s: number }[]
}) {
  const uid = useApp((s) => s.uid)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [speed, setSpeed] = useState(1)
  const [playing, setPlaying] = useState(false)
  const [videoTime, setTime] = useState(0)
  const [offset, setOffset] = useState(0)   // 手动对齐：视频相对动画的时间偏移
  const [error, setError] = useState('')
  const [signed, setSigned] = useState<string | null>(null)
  const fileName = useMemo(() => videoPath.split('/').pop() ?? '', [videoPath])

  // 短时签名 URL（视频按用户隔离，<img>/video 带不了令牌头）
  useEffect(() => {
    api.mediaSign(uid, fileName)
      .then((s) => setSigned(`/api/media/${uid}/${encodeURIComponent(fileName)}?sig=${s.sig}&exp=${s.exp}`))
      .catch((e) => setError((e as ApiError).message))
  }, [uid, fileName])

  // 卸载清理：暂停视频（3D 资源由 Viewer 自行释放）
  useEffect(() => () => { videoRef.current?.pause() }, [])

  // 当前视频所处阶段（按 offset 对齐到动画时间轴）
  const activePhase = useMemo(() => {
    const t = videoTime - offset
    return phases.find((p) => t >= p.start_s && t <= p.end_s) ?? null
  }, [videoTime, offset, phases])

  function toggle() {
    const v = videoRef.current
    if (!v) return
    if (v.paused) { v.play().catch(() => {}); setPlaying(true) }
    else { v.pause(); setPlaying(false) }
  }

  return (
    <div className="space-y-3">
      {error && <ErrorBox message={error} />}
      <div className="grid gap-3 sm:grid-cols-2">
        {/* 左：用户视频 */}
        <div className="card !p-2">
          <p className="px-1 pb-1 text-2xs font-semibold text-muted">我的视频</p>
          {signed ? (
            <video ref={videoRef} src={signed} controls={false}
                   className="w-full rounded-lg bg-black"
                   onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
                   onEnded={() => setPlaying(false)}
                   playsInline />
          ) : (
            <div className="flex h-40 items-center justify-center rounded-lg bg-canvas text-xs text-muted">
              签名生成中…
            </div>
          )}
        </div>
        {/* 右：三维教学动画 */}
        <div className="card !p-2">
          <p className="px-1 pb-1 text-2xs font-semibold text-muted">
            三维教学动画（参考，非正确性标准）
          </p>
          <Suspense fallback={
            <div className="flex h-40 items-center justify-center rounded-lg bg-canvas text-xs text-muted">
              三维组件加载中…
            </div>}>
            <Exercise3DViewer key={demo.model_url} demo={demo} />
          </Suspense>
        </div>
      </div>

      {/* 对照控制条 */}
      <div className="card !p-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button className="btn-soft btn" onClick={toggle} aria-label="播放/暂停视频">
            {playing ? <Pause size={14} /> : <Play size={14} />}
            {playing ? '暂停' : '播放'}
          </button>
          <Select value={String(speed)} onChange={(e) => {
            const v = Number(e.target.value); setSpeed(v)
            if (videoRef.current) videoRef.current.playbackRate = v
          }} className="w-24">
            {[0.25, 0.5, 1, 1.5].map((v) => (
              <option key={v} value={v}>{v}x 速度</option>
            ))}
          </Select>
          <label className="flex items-center gap-1.5">
            <span className="text-muted">手动对齐（视频前移）</span>
            <input type="range" min={-3} max={3} step={0.1} value={offset}
                   onChange={(e) => setOffset(Number(e.target.value))}
                   className="w-28" aria-label="手动对齐偏移（秒）" />
            <span className="nums w-10 text-muted">{offset.toFixed(1)}s</span>
          </label>
          <span className="nums ml-auto text-faint">
            视频 {videoTime.toFixed(1)}s
            {activePhase ? ` · 阶段 #${activePhase.rep}` : ''}
          </span>
        </div>
        {phases.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {phases.map((p) => (
              <button key={p.rep} className="tag bg-ink/5 text-muted hover:bg-accent-soft"
                      onClick={() => {
                        const v = videoRef.current
                        if (v) { v.currentTime = Math.max(0, p.start_s); setTime(p.start_s) }
                      }}>
                跳到 #{p.rep}（{p.start_s}s）
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 阶段教学提示 */}
      {activePhase && (
        <div className="rounded-xl bg-canvas p-3 text-xs leading-relaxed text-muted">
          当前视频处于阶段 #{activePhase.rep}（{activePhase.start_s}–{activePhase.end_s}s，
          谷值 {activePhase.peak_s}s）。对照时注意：
          身体比例、动作节奏、拍摄视角、器械与个人活动范围都可能与动画不同——
          <b className="text-ink">没有与参考动画重合不等于动作错误</b>。
        </div>
      )}
    </div>
  )
}
