// 媒体共享工具：短时签名 URL（含过期预刷新）+ 统一占位封面。
// 无媒体时使用统一占位视觉（首字母 + 品牌色渐变），不使用未授权第三方素材。
// 封面查询：模块级缓存 + IntersectionObserver 懒加载（M6.1：动作库不再逐卡全量请求）。
import { useEffect, useState } from 'react'
import { Dumbbell } from 'lucide-react'
import { api } from '../api'

interface SignedUrl { url: string; exp: number }

const signCache = new Map<string, Promise<SignedUrl>>()

/** 媒体签名 URL（10 分钟短时 sig；过期前 60s 自动重签，本机无令牌模式回退无签名地址） */
export function signedMediaUrl(uid: string, path: string): Promise<string> {
  const file = path.match(/media\/[^/]+\/([^/]+)$/)?.[1] || ''
  if (!file) return Promise.resolve('')
  const key = `${uid}/${file}`
  const cached = signCache.get(key)
  if (cached) {
    return cached.then((s) =>
      s.exp - Date.now() / 1000 > 60 ? s.url : (signCache.delete(key), signedMediaUrl(uid, path)))
  }
  const p = api.mediaSign(uid, file)
    .then((s) => ({ url: `/api/media/${uid}/${file}?sig=${s.sig}&exp=${s.exp}`, exp: s.exp }))
    .catch(() => ({ url: `/api/media/${uid}/${file}`, exp: Number.MAX_SAFE_INTEGER }))
  signCache.set(key, p)
  return p.then((s) => s.url)
}

export function useSignedMedia(uid: string, path?: string | null): string {
  const [src, setSrc] = useState('')
  useEffect(() => {
    if (!path) { setSrc(''); return }
    let alive = true
    signedMediaUrl(uid, path).then((u) => { if (alive) setSrc(u) })
    return () => { alive = false }
  }, [uid, path])
  return src
}

/** 元素进入视口（含 200px 预载边距）后返回 true；不支持 IO 的环境直接视为可见 */
function useInView(el: HTMLElement | null): boolean {
  const [inView, setInView] = useState(false)
  useEffect(() => {
    if (inView || !el) return
    if (typeof IntersectionObserver === 'undefined') { setInView(true); return }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) { setInView(true); io.disconnect() }
      },
      { rootMargin: '200px' })
    io.observe(el)
    return () => io.disconnect()
  }, [inView, el])
  return inView
}

// 封面结果缓存：uid/exId -> { 封面 URL 或 null（已确认无封面）, 写入时间 }。
// 同一动作全站只查一次；带 TTL（用户在别端关联媒体后最迟 5 分钟自动刷新），
// 本端发生媒体变更时可用 invalidateExerciseCover 立即失效。
const COVER_TTL = 5 * 60 * 1000
const COVER_CACHE_MAX = 400
interface CoverEntry { v: string | null; at: number }
const coverCache = new Map<string, CoverEntry>()

/** 封面缓存失效：省略参数清空全部；只给 uid 清该用户；再给 exerciseId 精确清一条 */
export function invalidateExerciseCover(uid?: string, exerciseId?: string): void {
  if (!uid) { coverCache.clear(); return }
  if (exerciseId) { coverCache.delete(`${uid}/${exerciseId}`); return }
  for (const k of [...coverCache.keys()]) {
    if (k.startsWith(`${uid}/`)) coverCache.delete(k)
  }
}

const coverFresh = (key: string): string | null | undefined => {
  const e = coverCache.get(key)
  if (!e) return undefined
  if (Date.now() - e.at > COVER_TTL) { coverCache.delete(key); return undefined }
  return e.v
}

/** 某动作的用户教学媒体（封面优先）。inView=false 时不发请求。
 *  返回值：undefined=未加载/加载中，null=确认无封面 */
export function useExerciseCover(uid: string, exerciseId: string | undefined | null,
                                 inView: boolean): string | null | undefined {
  const key = exerciseId ? `${uid}/${exerciseId}` : ''
  const [state, setState] = useState<{ k: string; v: string | null | undefined }>(
    () => ({ k: key, v: key ? coverFresh(key) : null }))
  if (state.k !== key) setState({ k: key, v: key ? coverFresh(key) : null })
  const cover = state.k === key ? state.v : undefined

  useEffect(() => {
    if (!key || !inView) return
    const cached = coverFresh(key)
    if (cached !== undefined) { setState({ k: key, v: cached }); return }
    let alive = true
    fetch(`/api/users/${uid}/exercise-media?exercise_id=${encodeURIComponent(exerciseId!)}`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json())
      .then((r) => {
        const link = ((r.links || []) as { cover_path: string | null }[]).find((l) => l.cover_path)
        return link?.cover_path ? signedMediaUrl(uid, link.cover_path) : null
      })
      .catch(() => null)
      .then((url) => {
        if (coverCache.size >= COVER_CACHE_MAX) {
          coverCache.delete(coverCache.keys().next().value as string)
        }
        coverCache.set(key, { v: url, at: Date.now() })
        if (alive) setState({ k: key, v: url })
      })
    return () => { alive = false }
  }, [key, inView, uid, exerciseId])
  return cover
}

const COVER_TONES = [
  ['#223328', '#18251D'], ['#2A3A2E', '#1B2A20'], ['#1F3229', '#16241C'],
  ['#28382A', '#18251D'], ['#233B31', '#17251E'],
]

/** 统一占位封面：首字母 + 深墨渐变（确定性，同动作同色） */
export function CoverPlaceholder({ name, className = '', iconSize = 22 }: {
  name: string; className?: string; iconSize?: number
}) {
  let hash = 0
  for (const c of name) hash = (hash * 31 + c.charCodeAt(0)) >>> 0
  const [from, to] = COVER_TONES[hash % COVER_TONES.length]
  return (
    <div className={`relative flex items-center justify-center overflow-hidden ${className}`}
         style={{ background: `linear-gradient(135deg, ${from}, ${to})` }} aria-hidden>
      <Dumbbell size={iconSize * 2.6} className="absolute -bottom-2 -right-2 text-white/6" />
      <span className="font-bold text-accent/90" style={{ fontSize: iconSize }}>
        {name.slice(0, 1).toUpperCase()}
      </span>
    </div>
  )
}

/** 动作封面：进入视口才请求媒体列表；用户上传封面优先，无媒体回退统一占位 */
export function ExerciseCover({ uid, exerciseId, name, className = '', iconSize = 22 }: {
  uid: string; exerciseId?: string | null; name: string; className?: string; iconSize?: number
}) {
  const [el, setEl] = useState<HTMLDivElement | null>(null)
  const inView = useInView(el)
  const cover = useExerciseCover(uid, exerciseId, inView)
  if (cover === undefined) {
    return <div ref={setEl} className={`animate-pulse-soft bg-ink/6 ${className}`} aria-hidden />
  }
  if (cover) {
    return <img alt={`${name} 封面`} src={cover} className={`object-cover ${className}`} />
  }
  return <CoverPlaceholder name={name} className={className} iconSize={iconSize} />
}
