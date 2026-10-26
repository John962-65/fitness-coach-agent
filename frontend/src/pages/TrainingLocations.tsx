import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, MapPin, Plus, Settings2, Trash2 } from 'lucide-react'
import { api } from '../api'
import { Button, ErrorBox, Input, Sheet, Spinner, SubHeader } from '../components/Bits'
import { useApp } from '../store'
import {
  EquipmentItem, LocationKind, LocationsResponse, TrainingLocation,
} from '../types'

const KIND_LABEL: Record<LocationKind, string> = {
  gym: '健身房', home: '居家', outdoor: '户外', custom: '自定义',
}

type LocationDraft = {
  name: string
  kind: LocationKind
  required: string[]
  optional: string[]
}

const emptyDraft = (): LocationDraft => ({
  name: '', kind: 'custom', required: [], optional: [],
})

export default function TrainingLocations() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [data, setData] = useState<LocationsResponse | null>(null)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<LocationDraft>(emptyDraft())
  const [deleting, setDeleting] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [eqOpen, setEqOpen] = useState(false)
  const [eqEditing, setEqEditing] = useState<string | null>(null)
  const [eqName, setEqName] = useState('')
  const [eqCategory, setEqCategory] = useState('accessory')
  const [eqFulfills, setEqFulfills] = useState('')
  const [eqAliases, setEqAliases] = useState('')

  const load = () => api.locations(uid).then(setData).catch((e) => setError(e.message))
  useEffect(() => { load() }, [uid]) // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !data) return <ErrorBox message={error} />
  if (!data) return <Spinner />

  const beginEdit = (loc?: TrainingLocation) => {
    setEditing(loc?.id ?? 'new')
    setDraft(loc ? {
      name: loc.name, kind: loc.kind,
      required: [...loc.required_equipment_ids],
      optional: [...loc.optional_equipment_ids],
    } : emptyDraft())
    setError('')
  }

  const setEquipmentState = (id: string, state: 'none' | 'required' | 'optional') => {
    setDraft((d) => ({
      ...d,
      required: state === 'required'
        ? [...new Set([...d.required, id])] : d.required.filter((x) => x !== id),
      optional: state === 'optional'
        ? [...new Set([...d.optional, id])] : d.optional.filter((x) => x !== id),
    }))
  }

  const equipmentState = (id: string) =>
    draft.required.includes(id) ? 'required'
      : draft.optional.includes(id) ? 'optional' : 'none'

  const saveLocation = async () => {
    if (!draft.name.trim()) { setError('地点名称必填'); return }
    setSaving(true); setError('')
    const payload = {
      name: draft.name.trim(), kind: draft.kind,
      required_equipment: draft.required, optional_equipment: draft.optional,
    }
    try {
      if (editing === 'new') await api.createLocation(uid, payload)
      else if (editing != null) await api.updateLocation(uid, editing, payload)
      setEditing(null)
      await load()
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  const beginEquipment = (eq?: EquipmentItem) => {
    setEqEditing(eq?.id ?? null)
    setEqName(eq?.name ?? '')
    setEqCategory(eq?.category ?? 'accessory')
    setEqFulfills(eq?.fulfills ?? '')
    setEqAliases((eq?.aliases || []).join('、'))
    setEqOpen(true)
    setError('')
  }

  const saveEquipment = async () => {
    if (!eqName.trim()) { setError('器械名称必填'); return }
    setSaving(true); setError('')
    const payload = {
      name: eqName.trim(), category: eqCategory,
      aliases: eqAliases.split(/[、,，]/).map((x) => x.trim()).filter(Boolean),
      fulfills: eqFulfills || null,
    }
    try {
      if (eqEditing) await api.updateEquipment(uid, eqEditing, payload)
      else await api.createEquipment(uid, payload)
      setEqName(''); setEqAliases(''); setEqFulfills('')
      setEqEditing(null); setEqOpen(false)
      await load()
    } catch (e) { setError((e as Error).message) }
    finally { setSaving(false) }
  }

  return (
    <div className="mx-auto w-full max-w-3xl">
      <SubHeader title="训练地点与器械" sub="当前地点决定动作可用性；已有计划不会因切换地点被自动删除"
                 onBack={() => navigate('/training')} />
      {error && <div className="mb-3"><ErrorBox message={error} /></div>}

      <div className="space-y-3">
        {data.locations.map((loc) => (
          <div key={loc.id} className="card">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <MapPin size={16} className="text-accent-deep" />
                  <h2 className="truncate text-base font-bold">{loc.name}</h2>
                  {loc.is_current && <span className="tag bg-accent-soft text-accent-deep">当前</span>}
                  <span className="tag border border-line text-muted">{KIND_LABEL[loc.kind]}</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">
                  必需：{loc.required_equipment.map((x) => x.name).join('、') || '未配置'}
                  {loc.optional_equipment.length > 0
                    && ` · 可选：${loc.optional_equipment.map((x) => x.name).join('、')}`}
                </p>
              </div>
              <Settings2 size={16} className="mt-1 shrink-0 text-faint" />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {!loc.is_current && (
                <Button className="btn-sm" onClick={() => api.selectLocation(uid, loc.id)
                  .then(load).catch((e) => setError(e.message))}>
                  <Check size={14} /> 设为当前
                </Button>
              )}
              <Button variant="ghost" className="btn-sm" onClick={() => beginEdit(loc)}>编辑</Button>
              {deleting === loc.id ? (
                <>
                  <Button variant="danger" className="btn-sm" onClick={() => api.deleteLocation(uid, loc.id)
                    .then(() => { setDeleting(null); return load() })
                    .catch((e) => setError(e.message))}>确认删除</Button>
                  <Button variant="ghost" className="btn-sm" onClick={() => setDeleting(null)}>取消</Button>
                </>
              ) : (
                <Button variant="ghost" className="btn-sm" onClick={() => setDeleting(loc.id)}>
                  <Trash2 size={14} /> 删除
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>

      <Button block variant="ghost" className="mt-3" onClick={() => beginEdit()}>
        <Plus size={15} /> 新增训练地点
      </Button>

      <div className="card mt-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold">我的自定义器械</h2>
            <p className="mt-1 text-xs text-muted">只对你可见；可映射为系统器械类型参与可用性判断</p>
          </div>
          <Button variant="ghost" className="btn-sm" onClick={() => beginEquipment()}>
            <Plus size={14} /> 添加
          </Button>
        </div>
        <ul className="mt-3 space-y-2">
          {data.equipment.filter((x) => x.scope === 'user').map((eq) => (
            <li key={eq.id} className="flex items-center gap-2 rounded-xl bg-canvas p-2.5">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{eq.name}</p>
                <p className="text-2xs text-muted">
                  {data.categories[eq.category] || eq.category}
                  {eq.fulfills && ` · 等效 ${data.equipment.find((x) => x.id === eq.fulfills)?.name || eq.fulfills}`}
                </p>
              </div>
              <button className="btn-plain" onClick={() => beginEquipment(eq)}>编辑</button>
              <button className="btn-plain !text-red-500" onClick={() => api.deleteEquipment(uid, eq.id)
                .then(load).catch((e) => setError(e.message))}>
                <Trash2 size={14} /> 删除
              </button>
            </li>
          ))}
          {!data.equipment.some((x) => x.scope === 'user') && (
            <li className="text-xs text-muted">还没有自定义器械。</li>
          )}
        </ul>
      </div>

      <Sheet open={editing !== null} onClose={() => setEditing(null)}
             title={editing === 'new' ? '新增训练地点' : '编辑训练地点'}>
        <label className="label">名称</label>
        <Input value={draft.name} placeholder="如 宿舍训练角"
               onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <label className="label mt-3">地点类型</label>
        <select className="input" value={draft.kind}
                onChange={(e) => setDraft({ ...draft, kind: e.target.value as LocationKind })}>
          {Object.entries(KIND_LABEL).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <p className="label mt-3">器械配置</p>
        <p className="mb-2 text-2xs leading-relaxed text-muted">
          必需器械用于可执行判断；可选器械也会计入当前地点可用性。
        </p>
        <ul className="space-y-1.5">
          {data.equipment.filter((eq) => eq.id !== 'bodyweight').map((eq: EquipmentItem) => (
            <li key={eq.id} className="flex items-center gap-2 rounded-lg bg-canvas px-2.5 py-2">
              <span className="min-w-0 flex-1 truncate text-xs">{eq.name}</span>
              <select className="input input-sm w-24" value={equipmentState(eq.id)}
                      aria-label={`${eq.name} 器械状态`}
                      onChange={(e) => setEquipmentState(
                        eq.id, e.target.value as 'none' | 'required' | 'optional')}>
                <option value="none">不需要</option>
                <option value="required">必需</option>
                <option value="optional">可选</option>
              </select>
            </li>
          ))}
        </ul>
        <Button block className="mt-4" disabled={saving} onClick={saveLocation}>
          {saving ? '保存中…' : '保存地点'}
        </Button>
      </Sheet>

      <Sheet open={eqOpen} onClose={() => setEqOpen(false)}
             title={eqEditing ? '编辑自定义器械' : '添加自定义器械'}>
        <label className="label">名称</label>
        <Input value={eqName} placeholder="如 家里的可调哑铃"
               onChange={(e) => setEqName(e.target.value)} />
        <label className="label mt-3">分类</label>
        <select className="input" value={eqCategory}
                onChange={(e) => setEqCategory(e.target.value)}>
          {Object.entries(data.categories).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <label className="label mt-3">等效系统器械（可选）</label>
        <select className="input" value={eqFulfills}
                onChange={(e) => setEqFulfills(e.target.value)}>
          <option value="">不映射</option>
          {data.equipment.filter((x) => x.scope === 'system' && x.id !== 'bodyweight')
            .map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        <label className="label mt-3">别名（顿号/逗号分隔）</label>
        <Input value={eqAliases} placeholder="如 小哑铃、可调哑铃"
               onChange={(e) => setEqAliases(e.target.value)} />
        <Button block className="mt-4" disabled={saving} onClick={saveEquipment}>
          {saving ? '保存中…' : eqEditing ? '保存修改' : '添加器械'}
        </Button>
      </Sheet>
    </div>
  )
}
