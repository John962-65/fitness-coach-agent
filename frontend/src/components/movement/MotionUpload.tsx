import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Select } from '../../components/Bits'
import { useApp } from '../../store'

/** 上传动作视频：视角必选（拍摄规范提示）；轮询至分析完成 */
export default function MotionUpload({ exerciseId, exerciseName, onDone }: {
  exerciseId: string; exerciseName: string; onDone: (analysisId: number) => void }) {
  const uid = useApp((s) => s.uid)
  const fileRef = useRef<HTMLInputElement>(null)
  const [view, setView] = useState('side')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  async function upload(file: File) {
    setBusy(true); setError(''); setNote('已上传，本地姿态推理中…')
    const form = new FormData()
    form.append('exercise_id', exerciseId)
    form.append('view', view)
    form.append('video', file)
    try {
      const res = await fetch(`/api/users/${uid}/motion-analyses`,
        { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) {
        setError(body.detail?.error || '上传失败'); setNote(''); return
      }
      const aid = body.analysis_id as number
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1500))
        const list = await api.motionAnalyses(uid, exerciseId) as
          { analyses: { id: number; status: string }[] }
        const me = (list.analyses || []).find((x) => x.id === aid)
        if (me && me.status !== 'processing') {
          setNote(''); onDone(aid); return
        }
      }
      setNote('分析仍在进行（本地推理较慢），稍后到「历史技术记录」刷新查看')
    } catch (e) {
      setError((e as ApiError).message); setNote('')
    } finally { setBusy(false) }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Select value={view} onChange={(e) => setView(e.target.value)} className="w-36">
          <option value="side">侧面（推荐）</option>
          <option value="front">正面（仅深蹲部分规则）</option>
          <option value="back">背面</option>
        </Select>
        <input ref={fileRef} type="file" accept="video/mp4,video/webm,video/quicktime,video/x-m4v"
               className="hidden"
               onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }} />
        <Button className="flex-1" disabled={busy}
                onClick={() => fileRef.current?.click()}>
          <Upload size={15} /> {busy ? '处理中…' : `上传${exerciseName}视频`}
        </Button>
      </div>
      <p className="text-2xs leading-relaxed text-faint">
        拍摄规范：全身入镜、固定机位、侧面拍摄（肩/髋/膝/踝清晰可见）、光线充足。
        视频仅用于本人分析（不上传公共库）；mp4/webm ≤200MB。
      </p>
      {note && <p className="text-xs text-accent-deep">{note}</p>}
      {error && <ErrorBox message={error} />}
    </div>
  )
}
