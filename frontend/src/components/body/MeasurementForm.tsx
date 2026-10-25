import { useState } from 'react'
import { api, ApiError } from '../../api'
import { Button, ErrorBox, Input, Select, Sheet, Textarea } from '../../components/Bits'
import { useApp } from '../../store'
import { BODY_METRICS, MEASUREMENT_METHODS } from '../../lib/body'
import type { BodyMeasurement } from '../../types'

/** 快速记录 / 编辑测量：指标全部可选（至少一项）；成分类必须带方法 */
export default function MeasurementForm({ editing, onClose, onSaved }:
  { editing: BodyMeasurement | null; onClose: () => void; onSaved: () => void }) {
  const uid = useApp((s) => s.uid)
  const [form, setForm] = useState<Record<string, string>>(() => {
    if (!editing) return { weight_kg: '', waist_cm: '', hip_cm: '', chest_cm: '',
                           body_fat_percent: '', muscle_mass_kg: '',
                           measurement_method: '', device_source: '', notes: '',
                           local_date: new Date().toISOString().slice(0, 10) }
    const out: Record<string, string> = { measurement_method: editing.measurement_method ?? '',
                                          device_source: editing.device_source ?? '',
                                          notes: editing.notes ?? '',
                                          local_date: editing.local_date }
    for (const m of BODY_METRICS) {
      out[m.key] = editing[m.key] != null ? String(editing[m.key]) : ''
    }
    return out
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const needsMethod = form.body_fat_percent.trim() !== '' || form.muscle_mass_kg.trim() !== ''

  async function save() {
    setBusy(true); setError('')
    try {
      const data = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== ''))
      if (editing) {
        await api.updateBodyMeasurement(uid, editing.id, {
          expected_revision: editing.revision, data,
          reason: form.notes_reason ?? '编辑测量',
          evidence: form.evidence || '用户在身体页手动修改',
        })
      } else {
        await api.addBodyMeasurement(uid, data,
          `body-${Date.now().toString(36)}`)
      }
      onSaved(); onClose()
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setBusy(false) }
  }

  return (
    <Sheet open title={editing ? '编辑测量记录' : '快速记录'} onClose={onClose}>
      <div className="grid grid-cols-3 gap-2">
        {BODY_METRICS.map((m) => (
          <label key={m.key}>
            <span className="mb-1 block text-2xs text-muted">{m.label}（{m.unit}）</span>
            <Input inputMode="decimal" value={form[m.key]}
                   onChange={(e) => setForm({ ...form, [m.key]: e.target.value })}
                   placeholder="留空=未测" />
          </label>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label>
          <span className="mb-1 block text-2xs text-muted">测量日期</span>
          <Input type="date" value={form.local_date}
                 onChange={(e) => setForm({ ...form, local_date: e.target.value })} />
        </label>
        <label>
          <span className="mb-1 block text-2xs text-muted">
            测量方法{needsMethod ? ' *（成分数据必选）' : ''}
          </span>
          <Select value={form.measurement_method}
                  onChange={(e) => setForm({ ...form, measurement_method: e.target.value })}>
            <option value="">未选择</option>
            {MEASUREMENT_METHODS.map((m) => (
              <option key={m.key} value={m.key}>{m.label}</option>
            ))}
          </Select>
        </label>
      </div>
      {needsMethod && form.measurement_method === '' && (
        <p className="mt-1.5 text-2xs text-amber-700">
          体脂率/肌肉量为设备估算值：必须选择测量方法（不同设备结果不默认可比）。
        </p>
      )}
      <label className="mt-2 block">
        <span className="mb-1 block text-2xs text-muted">设备 / 来源备注</span>
        <Input value={form.device_source}
               onChange={(e) => setForm({ ...form, device_source: e.target.value })}
               placeholder="如：家用体脂秤 A" />
      </label>
      {editing && (
        <label className="mt-2 block">
          <span className="mb-1 block text-2xs text-muted">修改原因（留痕）</span>
          <Input value={form.evidence ?? ''}
                 onChange={(e) => setForm({ ...form, evidence: e.target.value })}
                 placeholder="如：当时记错了" />
        </label>
      )}
      <label className="mt-2 block">
        <span className="mb-1 block text-2xs text-muted">备注</span>
        <Textarea value={form.notes} rows={2}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      </label>
      {error && <div className="mt-2"><ErrorBox message={error} /></div>}
      <Button className="mt-3" block disabled={busy} onClick={save}>
        {busy ? '保存中…' : editing ? '保存修改（原值留痕）' : '保存'}
      </Button>
      <p className="mt-2 text-2xs leading-relaxed text-faint">
        只填测了的指标；未填写保持"未测量"，不会被当作 0 参与统计。
      </p>
    </Sheet>
  )
}
