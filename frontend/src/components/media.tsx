// 媒体共享工具：短时签名 URL（含过期预刷新）+ 统一占位封面。
// 无媒体时使用统一占位视觉（首字母 + 品牌色渐变），不使用未授权第三方素材。
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

/** 某动作的用户教学媒体（封面优先；只返回封面 URL，无则 null） */
export function useExerciseCover(uid: string, exerciseId: string | undefined | null):
  string | null | undefined {
  const [cover, setCover] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  useEffect(() => {
    if (!exerciseId) return
    let alive = true
    setPending(true)
    fetch(`/api/users/${uid}/exercise-media?exercise_id=${encodeURIComponent(exerciseId)}`, {
      headers: localStorage.getItem('fc-access-token')
        ? { 'X-Access-Token': localStorage.getItem('fc-access-token') || '' } : {},
    }).then((r) => r.json())
      .then((r) => {
        const link = ((r.links || []) as { cover_path: string | null }[]).find((l) => l.cover_path)
        return link?.cover_path ? signedMediaUrl(uid, link.cover_path) : null
      })
      .catch(() => null)
      .then((url) => { if (alive) { setCover(url); setPending(false) } })
    return () => { alive = false }
  }, [uid, exerciseId])
  return pending ? undefined : cover // undefined = 加载中
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

/** 动作封面：用户上传封面优先，无媒体回退统一占位 */
export function ExerciseCover({ uid, exerciseId, name, className = '', iconSize = 22 }: {
  uid: string; exerciseId?: string | null; name: string; className?: string; iconSize?: number
}) {
  const cover = useExerciseCover(uid, exerciseId)
  if (cover === undefined) {
    return <div className={`animate-pulse-soft bg-ink/6 ${className}`} aria-hidden />
  }
  if (cover) {
    return <img alt={`${name} 封面`} src={cover} className={`object-cover ${className}`} />
  }
  return <CoverPlaceholder name={name} className={className} iconSize={iconSize} />
}
