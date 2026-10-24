// M6.4-B B2.4：三维查看器回退 UI（加载中 / 加载失败 / WebGL 不可用）。
// 任何失败路径都不得白屏：给出明确文案与回到图文教学的出口。
import { Component, type ReactNode } from 'react'
import { AlertTriangle, Box, Loader2 } from 'lucide-react'
import { Button } from '../Bits'

/** WebGL 可用性探测（模块级缓存；失败即走降级，不渲染 Canvas） */
let webglProbe: boolean | null = null
export function webglSupported(): boolean {
  if (webglProbe !== null) return webglProbe
  try {
    const c = document.createElement('canvas')
    webglProbe = !!(window.WebGLRenderingContext
      && (c.getContext('webgl2') || c.getContext('webgl')))
  } catch {
    webglProbe = false
  }
  return webglProbe
}

export function ModelFallback({ mode, onFallback, onRetry }: {
  mode: 'loading' | 'error' | 'webgl'
  onFallback?: () => void
  onRetry?: () => void
}) {
  if (mode === 'loading') {
    return (
      <div className="flex aspect-[4/3] w-full flex-col items-center justify-center
                      gap-2 rounded-2xl border border-line bg-canvas text-sm text-muted">
        <Loader2 size={22} className="animate-spin" />
        三维模型加载中…（首次约 170 KB）
      </div>
    )
  }
  if (mode === 'error') {
    return (
      <div className="flex aspect-[4/3] w-full flex-col items-center justify-center
                      gap-3 rounded-2xl border border-line bg-canvas px-6 text-center">
        <AlertTriangle size={24} className="text-amber-500" />
        <div>
          <p className="text-sm font-medium text-ink">三维模型加载失败</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            网络异常或资源损坏时会出现此提示，可重试，或改看图文教学。
          </p>
        </div>
        <div className="flex gap-2">
          {onRetry && <Button size="sm" variant="soft" onClick={onRetry}>重试</Button>}
          {onFallback && <Button size="sm" onClick={onFallback}>查看图文教学</Button>}
        </div>
      </div>
    )
  }
  return (
    <div className="flex aspect-[4/3] w-full flex-col items-center justify-center
                    gap-3 rounded-2xl border border-line bg-canvas px-6 text-center">
      <Box size={24} className="text-muted" />
      <div>
        <p className="text-sm font-medium text-ink">当前环境不支持 WebGL，无法显示三维演示</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          三维演示为可选教学材料；图文教学与视频不受影响。
        </p>
      </div>
      {onFallback && <Button size="sm" onClick={onFallback}>查看图文教学</Button>}
    </div>
  )
}

/** 捕获 three/r3f 运行时异常（含加载失败）→ 统一回退 UI，绝不白屏 */
export class ViewerErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode }, { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
