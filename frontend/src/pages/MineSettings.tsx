// 设置与数据：高级设置 / 数据管理 / 离线同步失败处理（次级页面）
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import type { DeleteAccountResult, ImportApplyResult, ImportPreview } from '../api'
import {
  Button, Card, Input, Notice, PlainButton, Select, SubHeader, Tag,
} from '../components/Bits'
import { clearClientData } from '../lib/localData'
import { discardFailed, exportFailedJSON, failedItems, retryFailed } from '../offline'
import { useApp } from '../store'

const COUNT_LABELS: Record<string, string> = {
  profile: '档案', plans: '计划版本', checkins: '训练记录',
  checkin_revisions: '训练修订', meals: '饮食记录',
  custom_foods: '自定义食物', recipes: '食谱', body_measurements: '身体记录',
  body_measurement_revisions: '身体修订', recovery_checkins: '恢复记录',
  recovery_revisions: '恢复修订', symptom_episodes: '症状事件',
  symptom_observations: '症状观察', training_restrictions: '训练限制',
  training_restriction_revisions: '限制修订', personal_trials: '个人尝试',
  training_templates: '训练模板', user_equipment: '器械',
  training_locations: '训练地点', user_exercise: '动作反馈',
  knowledge_sources: '知识来源',
}

function download(blob: Blob, filename: string) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

export default function MineSettings() {
  const uid = useApp((s) => s.uid)
  const setUid = useApp((s) => s.setUid)
  const settings = useApp((s) => s.settings)
  const setRestSeconds = useApp((s) => s.setRestSeconds)
  const navigate = useNavigate()
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [backup, setBackup] = useState<unknown>(null)
  const [backupName, setBackupName] = useState('')
  const [importResult, setImportResult] = useState<ImportApplyResult | null>(null)
  const [opts, setOpts] = useState({
    restore_profile: false, activate_plan: false, replace_active_plan: false,
    accept_safety_import: false, require_media_integrity: false,
  })
  const [deleteText, setDeleteText] = useState('')
  const [deleteAck, setDeleteAck] = useState(false)
  const [deleteResult, setDeleteResult] = useState<DeleteAccountResult | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => { setError('') }, [uid])

  const exportAll = async (format: 'json' | 'csv') => {
    setError(''); setNote('')
    setBusy('export')
    try {
      const { blob, filename } = await api.exportData(uid, format)
      download(blob, filename)
      setNote(format === 'json'
        ? '完整备份已下载：包含结构化业务数据与媒体清单（媒体文件本体不包含在 JSON 中）'
        : '可读 CSV（ZIP）已下载：训练逐组展开，附完整性清单')
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy('') }
  }

  const chooseBackup = async (file: File) => {
    setError(''); setNote(''); setPreview(null); setImportResult(null)
    setBackupName(file.name)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const p = await api.importPreview(uid, data)
      setBackup(data)
      setPreview(p)
      setOpts({
        restore_profile: p.profile_restore_default,
        activate_plan: false,
        replace_active_plan: false,
        accept_safety_import: false,
        require_media_integrity: false,
      })
    } catch (e) {
      setBackup(null)
      setError((e as Error).message || '备份文件无法解析')
    }
  }

  const applyImport = async () => {
    if (!backup) return
    setError(''); setNote(''); setBusy('import')
    try {
      const result = await api.importApply(uid, backup, opts)
      setImportResult(result)
      setNote(result.mode === 'executable'
        ? '导入完成，备份中的计划已恢复为可执行版本；请刷新后核对。'
        : '导入完成：数据已归档，当前生效计划未自动切换；请刷新后核对。')
      setPreview(null)
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy('') }
  }

  const deleteAccount = async () => {
    setError(''); setNote('')
    if (deleteText !== 'DELETE' || !deleteAck) {
      setError('需要输入 DELETE 并勾选确认，才能删除账户')
      return
    }
    setBusy('delete')
    try {
      const result = await api.deleteAccount(uid)
      setDeleteResult(result)
      if (result.complete) {
        // 先清内存 uid（会触发一次空状态持久化），再清 localStorage，避免
        // fc-app-v1 又被订阅写回；最后回欢迎页。
        setUid('')
        await clearClientData()
        navigate('/welcome')
      } else {
        await clearClientData()
      }
      // complete=false：保留当前页展示残留项，不宣称彻底删除；用户手动返回
    } catch (e) {
      setError((e as Error).message || '删除失败，数据未被删除')
    } finally { setBusy('') }
  }

  const importRows = preview
    ? Object.entries(preview.counts)
      .filter(([, v]) => (v.to_insert ?? 0) > 0 || (v.duplicates ?? 0) > 0)
    : []

  return (
    <div className="mx-auto w-full max-w-3xl">
      <SubHeader title="设置与数据" sub="高级设置与数据管理" onBack={() => navigate('/mine')} />
      {note && (
        <p className="mb-3 rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
          {note}
        </p>
      )}
      {error && (
        <p className="mb-3 rounded-xl bg-red-50 px-3.5 py-2.5 text-center text-[13px] text-red-700">
          {error}
        </p>
      )}

      <div className="space-y-4">
        <Card title="训练设置">
          <label className="label" htmlFor="rest-seconds">组间休息默认时长（秒）</label>
          <div className="flex items-center gap-2">
            <Select id="rest-seconds" className="!w-32" value={settings.restSeconds}
                    onChange={(e) => setRestSeconds(Number(e.target.value))}>
              {[60, 90, 120, 150, 180].map((n) => <option key={n} value={n}>{n}</option>)}
            </Select>
            <span className="text-xs text-muted">完成正式组后自动开始倒计时</span>
          </div>
        </Card>

        <FailedSyncCard onChanged={() => setNote('离线队列已刷新')} />

        <Card title="完整备份与恢复"
              sub="导出所有结构化业务数据；恢复前必须预览，避免覆盖当前状态。">
          <div className="space-y-3">
            <Notice tone="blue">
              备份包含敏感健康数据（训练、饮食、身体、恢复、症状、限制、视频清单）。
              请只保存到可信位置；媒体文件本体不随 JSON 打包。
            </Notice>
            <div className="flex flex-wrap gap-2">
              <Button variant="ghost" disabled={!!busy}
                      onClick={() => exportAll('json')}>完整导出我的数据（JSON）</Button>
              <Button variant="ghost" disabled={!!busy}
                      onClick={() => exportAll('csv')}>导出可读 CSV（ZIP）</Button>
            </div>
            <div>
              <input ref={fileRef} type="file" accept="application/json,.json"
                     className="hidden"
                     onChange={(e) => {
                       const f = e.target.files?.[0]
                       if (f) void chooseBackup(f)
                       e.target.value = ''
                     }} />
              <Button variant="soft" block disabled={!!busy}
                      onClick={() => fileRef.current?.click()}>
                选择备份 JSON 并预览恢复
              </Button>
              {backupName && <p className="mt-1.5 text-xs text-muted">已选择：{backupName}</p>}
            </div>
          </div>

          {preview && (
            <div className="mt-4 space-y-3 rounded-2xl border border-line bg-canvas/60 p-3.5">
              <p className="text-sm font-semibold">恢复预览</p>
              <p className="text-xs text-muted">
                备份用户：{preview.exported_for || '（未知）'}；
                源生效计划：{preview.source_active_plan_version ?? '无'}；
                目标：{preview.target_user}
              </p>
              <div className="grid grid-cols-2 gap-1.5 text-xs sm:grid-cols-3">
                {importRows.map(([key, v]) => (
                  <div key={key} className="rounded-lg bg-surface px-2 py-1.5">
                    <span className="text-muted">{COUNT_LABELS[key] || key}：</span>
                    新增 {v.to_insert ?? 0}
                    {(v.duplicates ?? 0) > 0 && <span className="text-amber-700">，重复 {v.duplicates}</span>}
                  </div>
                ))}
              </div>
              {preview.conflicts.length > 0 && (
                <Notice tone="amber">
                  <span>
                    <strong>发现 {preview.conflicts.length} 个冲突</strong>（同版本不同内容等）。
                    默认保留目标当前版本；请先确认，再决定是否继续。
                  </span>
                </Notice>
              )}
              {preview.profile_conflict && (
                <p className="text-xs text-amber-700">
                  目标已建档且档案与备份不同；不勾选“恢复档案”将保留当前档案。
                </p>
              )}
              {preview.safety_review.items.length > 0 && (
                <Notice tone="amber">
                  <div>
                    <p className="font-semibold">安全字段需要你确认</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs">
                      {preview.safety_review.items.map((x, i) => <li key={i}>{x.detail}</li>)}
                    </ul>
                    <p className="mt-1 text-xs">
                      不勾选下方“按备份声明导入安全字段”时，医疗筛查/训练许可会被置为
                      待本人确认；专业限制仍保持生效。
                    </p>
                  </div>
                </Notice>
              )}
              <Notice tone="blue">
                <span className="text-xs">
                  媒体：检查 {preview.media_report.checked} 项，通过 {preview.media_report.ok.length}，
                  缺失 {preview.media_report.missing.length}，损坏 {preview.media_report.corrupt.length}，
                  未验证 {preview.media_report.unverified.length}，越界路径 {preview.media_report.unsafe_path.length}。
                  {preview.media_report.note}
                </span>
              </Notice>
              <div className="space-y-2 text-sm">
                <label className="flex items-start gap-2">
                  <input type="checkbox" checked={opts.restore_profile}
                         onChange={(e) => setOpts({ ...opts, restore_profile: e.target.checked })} />
                  <span>恢复档案（覆盖当前档案；仅在你确认备份属于本人时勾选）</span>
                </label>
                <label className="flex items-start gap-2">
                  <input type="checkbox" checked={opts.accept_safety_import}
                         onChange={(e) => setOpts({ ...opts, accept_safety_import: e.target.checked })} />
                  <span>按备份声明导入安全字段（医疗筛查、专业评估；系统不会独立核验）</span>
                </label>
                <label className="flex items-start gap-2">
                  <input type="checkbox" checked={opts.activate_plan}
                         disabled={!preview.can_activate_plan}
                         onChange={(e) => setOpts({ ...opts, activate_plan: e.target.checked })} />
                  <span>把备份中的生效计划恢复为可执行版本（需通过医疗/限制/隔离检查）</span>
                </label>
                {!preview.can_activate_plan && (
                  <ul className="list-disc pl-6 text-xs text-amber-700">
                    {preview.activation_blockers.slice(0, 5).map((b, i) => <li key={i}>{b}</li>)}
                  </ul>
                )}
                <label className="flex items-start gap-2">
                  <input type="checkbox" checked={opts.replace_active_plan}
                         disabled={!opts.activate_plan}
                         onChange={(e) => setOpts({ ...opts, replace_active_plan: e.target.checked })} />
                  <span>目标已有生效计划时，用备份版本替换（必须显式确认）</span>
                </label>
                <label className="flex items-start gap-2">
                  <input type="checkbox" checked={opts.require_media_integrity}
                         onChange={(e) => setOpts({ ...opts, require_media_integrity: e.target.checked })} />
                  <span>媒体缺失/哈希不符时拒绝导入（默认仅报告）</span>
                </label>
              </div>
              <div className="flex gap-2">
                <Button variant="primary" block disabled={!!busy}
                        onClick={applyImport}>
                  {busy === 'import' ? '导入中…' : '确认导入'}
                </Button>
                <Button variant="ghost" disabled={!!busy}
                        onClick={() => { setPreview(null); setBackup(null); setBackupName('') }}>
                  取消
                </Button>
              </div>
            </div>
          )}

          {importResult && (
            <Notice tone="brand">
              <div className="text-xs">
                <p className="font-semibold">
                  导入完成（{importResult.mode === 'executable' ? '可执行计划' : '归档模式'}）
                </p>
                <p>新增：{Object.entries(importResult.inserted)
                  .filter(([, n]) => n > 0)
                  .map(([k, n]) => `${COUNT_LABELS[k] || k} ${n}`)
                  .join('、') || '无'}</p>
                {importResult.warnings.length > 0 && <p>提示：{importResult.warnings.join('；')}</p>}
                {importResult.needs_review.length > 0 && <p>需复核：{importResult.needs_review.join('；')}</p>}
                {importResult.activation_blocked.length > 0 && (
                  <p>计划未激活：{importResult.activation_blocked.slice(0, 3).join('；')}</p>
                )}
                <Button variant="ghost" size="sm" className="mt-2"
                        onClick={() => window.location.reload()}>刷新页面查看</Button>
              </div>
            </Notice>
          )}
        </Card>

        <Card title="删除账户及个人数据"
              sub="不可逆：删除数据库记录、媒体、子表与可归属日志，并清理本机缓存。">
          {!deleteResult ? (
            <div className="space-y-3">
              <Notice tone="amber">
                删除前请先导出备份。部署方备份/快照可能按政策保留最多
                30 天，需运维在期限内清除；应用内不保留副本。
              </Notice>
              <Input value={deleteText} onChange={(e) => setDeleteText(e.target.value)}
                     placeholder="输入 DELETE 确认" />
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={deleteAck}
                       onChange={(e) => setDeleteAck(e.target.checked)} />
                <span>我理解删除不可逆，并已确认当前账号是我要删除的账号。</span>
              </label>
              <Button variant="danger" block disabled={!!busy}
                      onClick={deleteAccount}>
                {busy === 'delete' ? '删除中…' : '永久删除账户及个人数据'}
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              <Notice tone={deleteResult.complete ? 'blue' : 'amber'}>
                <div className="text-xs">
                  <p className="font-semibold">
                    {deleteResult.complete ? '账户及个人数据已删除' : '账户数据已删除，但仍有残留'}
                  </p>
                  <p>数据库行：{Object.values(deleteResult.rows).reduce((a, b) => a + b, 0)}；
                    媒体文件：{deleteResult.media_files_removed}</p>
                  {deleteResult.cleanup_errors.length > 0 && (
                    <p>待处理：{deleteResult.cleanup_errors.join('；')}</p>
                  )}
                  {deleteResult.outside_media_not_deleted.length > 0 && (
                    <p>未自动删除的外部路径：{deleteResult.outside_media_not_deleted.join('；')}</p>
                  )}
                  <p>{deleteResult.backup_notice}</p>
                </div>
              </Notice>
              <Button variant="ghost" block onClick={() => { setUid(''); navigate('/welcome') }}>
                返回欢迎页
              </Button>
            </div>
          )}
        </Card>

        <Card title="会话与访问">
          <div className="space-y-3">
            <div>
              <label className="label" htmlFor="switch-uid">切换用户</label>
              <div className="flex gap-2">
                <Input id="switch-uid" placeholder="切换到其他用户 ID"
                       onKeyDown={(e) => {
                         if (e.key === 'Enter') {
                           const v = (e.target as HTMLInputElement).value.trim()
                           if (v) { setUid(v); navigate('/today') }
                         } }} />
                <Button variant="ghost" className="shrink-0"
                        onClick={() => { setUid(''); navigate('/welcome') }}>新用户建档</Button>
              </div>
            </div>
            <div>
              <label className="label" htmlFor="fc-token-input">
                访问令牌（仅当服务设置了 API_ACCESS_TOKEN 时需要）
              </label>
              <div className="flex gap-2">
                <Input id="fc-token-input" type="password"
                       defaultValue={localStorage.getItem('fc-access-token') || ''}
                       placeholder="X-Access-Token" />
                <Button variant="ghost" className="shrink-0"
                        onClick={() => {
                          const v = (document.getElementById('fc-token-input') as HTMLInputElement).value.trim()
                          if (v) localStorage.setItem('fc-access-token', v)
                          else localStorage.removeItem('fc-access-token')
                          setNote(v ? '访问令牌已保存，后续请求自动携带' : '访问令牌已清除')
                        }}>保存</Button>
              </div>
            </div>
          </div>
        </Card>

        <Notice tone="amber">
          本系统不提供医疗诊断或治疗建议；涉及伤病、疾病、孕期、用药的内容默认隔离并建议咨询专业人员。
          视频估计与模型推断不构成医学结论。
        </Notice>
      </div>
    </div>
  )
}

/* ---------------- 同步失败记录（可重试/丢弃/导出，绝不静默删除） ---------------- */

function FailedSyncCard({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<Awaited<ReturnType<typeof failedItems>> | null>(null)
  const [msg, setMsg] = useState('')
  const refresh = useCallback(() => { failedItems().then(setItems) }, [])
  useEffect(() => { refresh() }, [refresh])

  if (items === null || items.length === 0) return null
  return (
    <Card title={<span className="flex items-center gap-1.5">
      <Tag tone="amber">同步失败</Tag> {items.length} 条待处理
    </span>}
          sub="这些训练记录因数据校验未通过而未能同步，已保留在本机——可重试、导出备份或丢弃。">
      <ul className="space-y-2">
        {items.map((f) => (
          <li key={f.id} className="rounded-xl bg-canvas p-3 text-xs leading-relaxed">
            <p className="text-ink">{new Date(f.at).toLocaleString('zh-CN')} · {f.type}</p>
            <p className="mt-0.5 text-red-600">失败原因：{f.error}</p>
            <PlainButton className="mt-1 !text-red-600"
                         onClick={async () => { await discardFailed(f.id); refresh() }}>丢弃这条</PlainButton>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <Button variant="ghost" className="flex-1"
                onClick={async () => {
                  const r = await retryFailed(async (u, t, d, sid) => {
                    await api.saveCheckin(u, t, d, sid)
                  })
                  setMsg(`重试完成：成功 ${r.synced}，仍失败 ${r.failed}，待网络 ${r.remaining}`)
                  refresh(); onChanged()
                }}>全部重试</Button>
        <Button variant="ghost" className="flex-1"
                onClick={async () => {
                  const blob = new Blob([await exportFailedJSON()], { type: 'application/json' })
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(blob)
                  a.download = `fitness-coach-sync-failed-${Date.now()}.json`
                  a.click(); URL.revokeObjectURL(a.href)
                }}>导出失败记录</Button>
      </div>
      {msg && <p className="mt-2 text-center text-xs text-accent-deep">{msg}</p>}
    </Card>
  )
}
