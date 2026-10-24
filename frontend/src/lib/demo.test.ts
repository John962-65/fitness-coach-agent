// M6.4-B B5.1：演示模式可用性纯函数测试
// - 不支持三维的动作不得误显示 3D 入口
// - 没有用户视频时不得显示视频入口
// - 图文教学始终可用；默认模式优先 3D → 视频 → 图文
import { describe, expect, it } from 'vitest'
import { defaultDemoMode, demoOptions, type Demo3D } from './demo'

const demo3d = (over: Partial<Demo3D> = {}): Demo3D => ({
  model_url: '/api/assets/exercise-3d/barbell_back_squat/barbell_back_squat.glb',
  animation_name: 'squat',
  duration: 3.6,
  loop: true,
  supported_views: ['front', 'side', 'back'],
  teaching_phases: [{ key: 'prep', label: '准备', t: [0, 0.5] }],
  ...over,
})

describe('demoOptions 演示入口', () => {
  it('无资源动作：只有图文教学', () => {
    expect(demoOptions(false, null)).toEqual([{ value: 'text', label: '图文教学' }])
  })

  it('仅有用户视频：视频 + 图文（无 3D 入口）', () => {
    const opts = demoOptions(true, null)
    expect(opts.map((o) => o.value)).toEqual(['video', 'text'])
  })

  it('有 3D 与视频：三个入口', () => {
    expect(demoOptions(true, demo3d()).map((o) => o.value))
      .toEqual(['video', 'model3d', 'text'])
  })

  it('demos.model_3d 缺 model_url（未授权被后端隐藏）时不显示 3D', () => {
    expect(demoOptions(false, demo3d({ model_url: '' })).map((o) => o.value))
      .toEqual(['text'])
    expect(demoOptions(false, undefined).map((o) => o.value)).toEqual(['text'])
  })
})

describe('defaultDemoMode 默认模式', () => {
  it('优先 3D → 视频 → 图文', () => {
    expect(defaultDemoMode(false, demo3d())).toBe('model3d')
    expect(defaultDemoMode(true, null)).toBe('video')
    expect(defaultDemoMode(false, null)).toBe('text')
  })
})
