// M6.4-B B2.4：动作三维演示查看器（默认导出，供 React.lazy 按需加载——
// three/r3f 只在用户选择三维模式后才进入 bundle，B2.5 加载策略）。
//
// 支持：播放/暂停、循环、0.25×–2× 倍速、拖动进度、正/侧/背预设视角、
// 单指旋转/双指缩放、重置相机、加载态/失败回退、WebGL 不可用降级、
// 教学阶段提示（标注为教学说明）。动画时间全部来自 AnimationAction 实际时间。
import { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { RotateCcw } from 'lucide-react'
import { AnimatedModel, disposeGltf, type PlayerApi } from './AnimatedModel'
import { PlaybackControls, type TeachingPhase } from './PlaybackControls'
import { CameraPresetButtons, CameraTween, DEFAULT_VIEW, type ViewPreset } from './CameraPresets'
import { ModelFallback, ViewerErrorBoundary, webglSupported } from './ModelFallback'

export interface Demo3DProps {
  model_url: string
  animation_name: string
  duration: number
  loop: boolean
  supported_views: string[]
  teaching_phases: TeachingPhase[]
  review_status?: string
}

export default function Exercise3DViewer({ demo, onFallback }: {
  demo: Demo3DProps
  onFallback?: () => void
}) {
  const [retryKey, setRetryKey] = useState(0)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const [contextLost, setContextLost] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [loop, setLoop] = useState(demo.loop)
  const [speed, setSpeed] = useState(1)
  const [time, setTime] = useState(0)
  const [preset, setPreset] = useState<ViewPreset | null>(null)
  const [activeView, setActiveView] = useState<ViewPreset | null>(DEFAULT_VIEW)
  const apiRef = useRef<PlayerApi | null>(null)
  const durationRef = useRef(demo.duration)
  const timeRef = useRef(0)

  // WebGL 不可用：直接降级 UI（绝不渲染 Canvas、绝不白屏）
  const webglOk = useRef(webglSupported()).current

  // 进度/阶段刷新：播放中 100ms 采样（真实动画时间）
  useEffect(() => {
    if (!playing || !apiRef.current) return
    const h = setInterval(() => {
      const t = apiRef.current?.getTime() ?? 0
      timeRef.current = t
      setTime(t)
    }, 100)
    return () => clearInterval(h)
  }, [playing, ready])

  // 卸载清理：释放 GLTF 缓存与 GPU 资源（B2.5）
  useEffect(() => () => disposeGltf(demo.model_url), [demo.model_url])

  const onTick = useCallback((t: number) => {
    timeRef.current = t
  }, [])

  const handleReady = useCallback((api: PlayerApi, duration: number) => {
    apiRef.current = api
    durationRef.current = duration
    setReady(true)
    setFailed(false)
  }, [])

  const toggle = useCallback(() => {
    const api = apiRef.current
    if (!api) return
    if (playing) {
      api.pause()
      setPlaying(false)
    } else {
      api.play()
      setPlaying(true)
    }
  }, [playing])

  const seek = useCallback((t: number) => {
    apiRef.current?.seek(t)
    timeRef.current = t
    setTime(t)
  }, [])

  const phase = demo.teaching_phases.find(
    (p) => time >= p.t[0] && time < (p.t[1] ?? durationRef.current)) || null

  if (!webglOk || contextLost) {
    return <ModelFallback mode="webgl" onFallback={onFallback} />
  }
  if (failed) {
    return (
      <ModelFallback mode="error"
                     onRetry={() => { setFailed(false); setReady(false); setRetryKey((k) => k + 1) }}
                     onFallback={onFallback} />
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-canvas">
      <div className="relative aspect-[4/3] w-full bg-[#F2F0E9]">
        {!ready && <ModelFallback mode="loading" />}
        <ViewerErrorBoundary
          fallback={<ModelFallback mode="error"
                                  onRetry={() => { setFailed(true) }}
                                  onFallback={onFallback} />}>
          <Canvas
            key={retryKey}
            dpr={[1, Math.min(typeof window !== 'undefined'
              ? window.devicePixelRatio : 1, 1.75)]}
            camera={{ position: [1.6, 1.35, 2.3], fov: 40 }}
            frameloop={playing ? 'always' : 'demand'}
            gl={{ antialias: true, powerPreference: 'high-performance' }}
            onCreated={({ gl }) => {
              gl.domElement.addEventListener('webglcontextlost', (e) => {
                e.preventDefault()
                setContextLost(true)
              })
            }}
            style={{ position: 'absolute', inset: 0 }}
            className={ready ? '' : 'opacity-0'}
          >
            <color attach="background" args={['#F2F0E9']} />
            <ambientLight intensity={0.75} />
            <directionalLight position={[2.5, 4, 3]} intensity={0.85} />
            <directionalLight position={[-2, 2, -2.5]} intensity={0.3} />
            <Suspense fallback={null}>
              <AnimatedModel
                url={demo.model_url}
                animationName={demo.animation_name}
                loop={loop}
                onTick={onTick}
                onReady={handleReady}
              />
            </Suspense>
            <OrbitControls makeDefault enablePan={false}
                           target={[0, 0.92, 0]}
                           minDistance={1.4} maxDistance={4.5}
                           maxPolarAngle={Math.PI * 0.55} />
            <CameraTween preset={preset} clearPreset={() => setPreset(null)} />
          </Canvas>
        </ViewerErrorBoundary>

        {ready && (
          <div className="pointer-events-none absolute inset-x-0 top-0 flex
                          items-start justify-between p-2.5">
            <div className="pointer-events-auto flex items-center gap-1.5">
              <CameraPresetButtons current={activeView}
                                   onSelect={(v) => { setPreset(v); setActiveView(v) }} />
              <button aria-label="重置视角" title="重置视角"
                      onClick={() => { setPreset(DEFAULT_VIEW); setActiveView(DEFAULT_VIEW) }}
                      className="flex size-8 items-center justify-center rounded-full
                                 border border-line bg-surface/90 text-muted shadow-card
                                 backdrop-blur transition-colors hover:text-ink">
                <RotateCcw size={14} />
              </button>
            </div>
            {demo.review_status && demo.review_status !== 'approved' && (
              <span className="pointer-events-auto tag bg-amber-50 text-amber-700">
                示例动画 · 未人工复核
              </span>
            )}
          </div>
        )}
      </div>

      {ready && (
        <PlaybackControls
          playing={playing} time={time} duration={durationRef.current}
          loop={loop} speed={speed} phase={phase}
          onToggle={toggle} onSeek={seek}
          onToggleLoop={() => setLoop((v) => !v)}
          onSpeed={(s) => { setSpeed(s); apiRef.current?.setSpeed(s) }}
        />
      )}
      <p className="border-t border-line bg-canvas/60 px-3 py-2 text-2xs leading-relaxed text-faint">
        三维演示为教学示例（比例与关节角度不代表对个人动作的判定）；
        单指拖动旋转、双指缩放、双击重置不适用请用右上角按钮。
      </p>
    </div>
  )
}
