import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'
import { OBS_KIND, QUALITY_TONE, type TechProfile } from '../../lib/movement'

/** 单次分析报告：视频质量 → 可观察特征 → 动作阶段时间轴 → 局限 */
export default function MotionAnalysisReport({ profile, result, note, restrictionHint }: {
  profile: TechProfile | null
  result: Record<string, unknown> | null
  note: string | null
  restrictionHint?: string | null
}) {
  const quality = profile?.video_quality
  const tone = QUALITY_TONE[quality?.status ?? 'unknown']
  const reps = profile?.phase_timestamps ?? []
  const faults = (result?.faults as { code: string; label?: string; hint?: string
                                      value?: number }[]) ?? []
  return (
    <div className="space-y-3">
      {/* 视频质量（先质量，再特征） */}
      <div className="card">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold">视频质量</p>
          <span className={`tag ${tone.cls}`}>
            {quality?.status === 'usable' && <CheckCircle2 size={12} className="mr-0.5 inline" />}
            {quality?.status === 'poor' && <AlertTriangle size={12} className="mr-0.5 inline" />}
            {tone.label}
          </span>
          {quality?.view && <span className="tag bg-ink/5 text-muted">{quality.view} 视角</span>}
          {profile?.model_version && (
            <span className="ml-auto text-2xs text-faint">{profile.model_version}</span>
          )}
        </div>
        {quality?.status === 'usable' ? (
          <p className="mt-1.5 text-xs leading-relaxed text-muted">
            检测覆盖率 {Math.round((quality.detection_ratio ?? 0) * 100)}% ·
            关键点完整率 {Math.round((quality.valid_ratio ?? 0) * 100)}%
          </p>
        ) : (
          <p className="mt-1.5 text-xs leading-relaxed text-amber-700">
            {(quality?.limitations ?? [note ?? '暂无质量信息']).join('；')}
            <br />质量不足的结果不可作为技术评估依据——请按拍摄规范重拍。
          </p>
        )}
      </div>

      {/* 可观察运动特征 */}
      {(profile?.motion_observations?.length ?? 0) > 0 && (
        <div className="card">
          <p className="text-sm font-semibold">可观察运动特征</p>
          <ul className="mt-2 space-y-1.5">
            {profile!.motion_observations.map((o, i) => (
              <li key={i} className="text-[13px] leading-relaxed">
                <span className="mr-1.5 tag bg-ink/5 text-muted">
                  {OBS_KIND[o.kind] ?? o.kind}
                </span>
                {o.text}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-2xs leading-relaxed text-faint">
            以上均为画面内二维投影观察：不是三维关节角，不含力矩/负荷推断；
            观察结果不代表动作"正确"或"错误"。
          </p>
        </div>
      )}

      {/* 故障码（可见几何提示） */}
      {faults.length > 0 && (
        <div className="card">
          <p className="text-sm font-semibold">可见几何提示（整段聚合）</p>
          <ul className="mt-2 space-y-1.5">
            {faults.map((f, i) => (
              <li key={i} className="text-[13px] leading-relaxed">
                <span className="mr-1.5 font-medium">{f.label ?? f.code}</span>
                {f.hint}
                {f.value !== undefined && `（数值 ${f.value}）`}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 动作阶段时间轴 */}
      {reps.length > 0 && (
        <div className="card">
          <p className="text-sm font-semibold">动作阶段（画面内估计）</p>
          <div className="mt-2 space-y-1.5">
            {reps.map((r) => (
              <div key={r.rep} className="flex items-center gap-2 text-xs">
                <span className="w-8 shrink-0 text-muted">#{r.rep}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-canvas">
                  <div className="relative h-full">
                    <div className="absolute inset-y-0 rounded-full bg-accent/50"
                         style={{ left: '0%', width: '100%' }} />
                  </div>
                </div>
                <span className="nums w-24 shrink-0 text-right text-muted">
                  {r.start_s}–{r.end_s}s
                </span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-2xs text-faint">
            峰值检测估计，不区分借力/半程；对照时可用这些时间手动对齐。
          </p>
        </div>
      )}

      {/* 康复限制联动（只读展示） */}
      {restrictionHint && (
        <div className="card border-amber-200 bg-amber-50/70">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-amber-800">
            <ShieldAlert size={15} /> 安全提醒
          </p>
          <p className="mt-1 text-xs leading-relaxed text-amber-800">{restrictionHint}</p>
          <p className="mt-1 text-2xs text-amber-700">
            观看教学与上传视频不受影响；是否执行该动作请遵循限制——训练修改需经修改提案确认。
          </p>
        </div>
      )}

      {/* 局限声明 */}
      <p className="px-1 text-2xs leading-relaxed text-faint">
        分析结果由本地模型（{profile?.model_version ?? '—'}）生成，状态 unreviewed
        （系统生成、未经人工逐条复核）；跨版本数值差异不解释为动作变化；
        本分析不构成医学诊断。
      </p>
    </div>
  )
}
