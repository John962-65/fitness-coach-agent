// 设置与数据：高级设置 / 数据管理 / 离线同步失败处理（次级页面）
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import {
  Button, Card, Input, Notice, PlainButton, Select, SubHeader, Tag,
} from '../components/Bits'
import { discardFailed, exportFailedJSON, failedItems, retryFailed } from '../offline'
import { useApp } from '../store'

export default function MineSettings() {
  const uid = useApp((s) => s.uid)
  const setUid = useApp((s) => s.setUid)
  const settings = useApp((s) => s.settings)
  const setRestSeconds = useApp((s) => s.setRestSeconds)
  const navigate = useNavigate()
  const [note, setNote] = useState('')
  const [profile, setProfile] = useState<null | Record<string, unknown>>(null)
  const [trials, setTrials] = useState<unknown>(null)
  const [view, setView] = useState<unknown>(null)

  useEffect(() => {
    // 导出数据用：与「我的」页一致的三份数据
    Promise.allSettled([
      api.profile(uid), api.approach(uid), api.trials(uid),
    ]).then(([p, a, t]) => {
      setProfile(p.status === 'fulfilled' ? (p.value as unknown as Record<string, unknown>) : null)
      setView(a.status === 'fulfilled' ? a.value : null)
      setTrials(t.status === 'fulfilled' ? t.value : null)
    })
  }, [uid])

  const exportData = () => {
    const blob = new Blob(
      [JSON.stringify({ profile, approach: view, trials, exported_at: new Date().toISOString() }, null, 2)],
      { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `fitness-coach-${uid}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <SubHeader title="设置与数据" sub="高级设置与数据管理" onBack={() => navigate('/mine')} />
      {note && (
        <p className="mb-3 rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
          {note}
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

        <Card title="数据管理">
          <div className="space-y-3">
            <Button variant="ghost" block onClick={exportData}>导出我的数据（JSON）</Button>
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
                <Input id="fc-token-input" type="password" defaultValue={localStorage.getItem('fc-access-token') || ''}
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
