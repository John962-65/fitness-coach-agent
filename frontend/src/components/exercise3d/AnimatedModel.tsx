// M6.4-B B2.4：骨骼动画模型（useGLTF + AnimationMixer，按真实动画时间驱动）。
// 播放/暂停/倍速/拖动均作用于 AnimationAction 的实际时间，不是只改进度条。
import { useEffect, useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { useGLTF } from '@react-three/drei'
import * as THREE from 'three'
import { clone as skeletonClone } from 'three/examples/jsm/utils/SkeletonUtils.js'

export interface PlayerApi {
  play(): void
  pause(): void
  seek(t: number): void
  setSpeed(s: number): void
  getTime(): number
}

interface Props {
  url: string
  animationName: string
  loop: boolean
  /** 进度回调（useFrame 内高频调用，只应写 ref，勿直接 setState） */
  onTick?: (t: number) => void
  onReady?: (api: PlayerApi, duration: number) => void
  /** 单次模式播完时触发（父组件同步按钮状态，P1-1） */
  onFinished?: () => void
}

export function AnimatedModel({ url, animationName, loop, onTick, onReady,
                                onFinished }: Props) {
  const gltf = useGLTF(url)
  const scene = useMemo(() => skeletonClone(gltf.scene), [gltf.scene])
  const mixer = useMemo(() => new THREE.AnimationMixer(scene), [scene])
  const invalidate = useThree((s) => s.invalidate)
  const actionRef = useRef<THREE.AnimationAction | null>(null)
  const pausedRef = useRef(true)
  const tickRef = useRef(onTick)
  tickRef.current = onTick

  // Action 生命周期只由模型与动画身份决定；loop 切换不重建（P1-1：
  // 重建会重置时间并暂停，而父组件 playing 状态不同步）
  useEffect(() => {
    const clip = gltf.animations.find((a) => a.name === animationName)
      || gltf.animations[0]
    if (!clip) return
    const action = mixer.clipAction(clip)
    action.reset()
    action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity)
    action.clampWhenFinished = !loop
    action.enabled = true
    action.paused = true   // 初始停在首帧，等用户点播放
    pausedRef.current = true
    action.play()
    actionRef.current = action
    mixer.update(0)
    invalidate()
    onReady?.({
      play: () => { pausedRef.current = false; action.paused = false },
      pause: () => { pausedRef.current = true; action.paused = true; invalidate() },
      seek: (t) => {
        action.time = ((t % clip.duration) + clip.duration) % clip.duration
        action.paused = pausedRef.current
        mixer.update(0)
        invalidate()   // frameloop='demand' 时手动触发重绘
      },
      setSpeed: (s) => { mixer.timeScale = s },
      getTime: () => action.time,
    }, clip.duration)
    return () => {
      mixer.stopAllAction()
      mixer.uncacheRoot(scene)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, mixer, animationName])

  // loop 模式切换：只改循环设置，保留当前时间/速度/暂停状态
  useEffect(() => {
    const action = actionRef.current
    if (!action) return
    action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce, Infinity)
    action.clampWhenFinished = !loop
    if (!loop && action.time >= (action.getClip().duration - 1e-6)) {
      action.time = 0        // 切单次时若已停在末帧，回到开头可重播
      mixer.update(0)
      invalidate()
    }
  }, [loop, mixer, invalidate])

  // 单次模式播完 → 通知父组件（按钮回到"播放"态）
  useEffect(() => {
    if (!onFinished) return
    const cb = () => onFinished()
    mixer.addEventListener('finished', cb)
    return () => mixer.removeEventListener('finished', cb)
  }, [mixer, onFinished])

  useFrame((_, dt) => {
    if (!pausedRef.current) mixer.update(dt)
    const a = actionRef.current
    if (a) tickRef.current?.(a.time)
  })

  return <primitive object={scene} />
}

/** 卸载时清理 GLTF 缓存（页面离开释放渲染资源，B2.5） */
export function disposeGltf(url: string) {
  try { useGLTF.clear(url) } catch { /* 已清理/未加载 */ }
}
