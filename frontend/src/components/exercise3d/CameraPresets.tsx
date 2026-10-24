// M6.4-B B2.4：相机预设（正面/侧面/背面 + 重置）与相机平滑过渡。
// 单指拖动旋转、双指缩放由 OrbitControls 提供；预设切换期间用户拖动即打断。
import { useEffect, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

export type ViewPreset = 'front' | 'side' | 'back'

const PRESET_POS: Record<ViewPreset, [number, number, number]> = {
  front: [0, 1.15, 2.9],
  side: [2.9, 1.15, 0],
  back: [0, 1.15, -2.9],
}
const TARGET = new THREE.Vector3(0, 0.92, 0)
export const DEFAULT_VIEW: ViewPreset = 'front'

/** 相机预设按钮（渲染在 Canvas 外的覆盖层） */
export function CameraPresetButtons({ current, onSelect }: {
  current: ViewPreset | null
  onSelect: (v: ViewPreset) => void
}) {
  const items: { v: ViewPreset; label: string }[] = [
    { v: 'front', label: '正面' }, { v: 'side', label: '侧面' }, { v: 'back', label: '背面' },
  ]
  return (
    <div className="flex gap-1 rounded-full border border-line bg-surface/90 p-0.5 shadow-card backdrop-blur">
      {items.map((it) => (
        <button key={it.v} onClick={() => onSelect(it.v)}
                aria-label={`${it.label}视角`}
                className={`rounded-full px-2.5 py-1 text-[11px] font-medium
                            transition-colors ${current === it.v
                  ? 'bg-night text-white' : 'text-muted hover:text-ink'}`}>
          {it.label}
        </button>
      ))}
    </div>
  )
}

/** Canvas 内：把相机平滑移动到预设位（用户拖动/缩放即取消动画） */
export function CameraTween({ preset, clearPreset }: {
  preset: ViewPreset | null
  clearPreset: () => void
}) {
  const camera = useThree((s) => s.camera)
  const controls = useThree((s) => s.controls) as
    { target: THREE.Vector3; update: () => void } | null
  const goal = useRef(new THREE.Vector3(...(preset ? PRESET_POS[preset] : PRESET_POS.front)))
  const active = useRef(false)

  useEffect(() => {
    if (preset) {
      goal.current.set(...PRESET_POS[preset])
      active.current = true
    }
  }, [preset])

  // 用户开始交互 → 停止过渡（OrbitControls 'start' 事件）
  useEffect(() => {
    const c = controls as unknown as
      { addEventListener: (e: 'start', cb: () => void) => void
        removeEventListener: (e: 'start', cb: () => void) => void } | null
    if (!c?.addEventListener) return
    const stop = () => { active.current = false; clearPreset() }
    c.addEventListener('start', stop)
    return () => c.removeEventListener('start', stop)
  }, [controls, clearPreset])

  useFrame(() => {
    if (!active.current) return
    camera.position.lerp(goal.current, 0.12)
    if (controls) {
      controls.target.lerp(TARGET, 0.2)
      controls.update()
    }
    if (camera.position.distanceTo(goal.current) < 0.01) {
      active.current = false
      clearPreset()
    }
  })
  return null
}
