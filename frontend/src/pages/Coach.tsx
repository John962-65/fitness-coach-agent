import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { Card, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { ChatMsg, Consultation, Proposal } from '../types'

// 操作预览：把统一协议的类型化操作转成一行人话（2.0 §4.2"展示方案依据与取舍"）
export function opSummary(op: Record<string, unknown>): string {
  const day = op.day ? String(op.day) : ''
  const ex = op.exercise ? String(op.exercise) : ''
  const idx = op.index !== undefined ? `#${Number(op.index) + 1}` : ''
  switch (op.op) {
    case 'add_exercise': return `${day} 新增 ${ex}（${op.sets}×${op.reps}）`
    case 'remove_exercise': return `${day} 移除 ${ex || idx}`
    case 'replace_exercise': return `${day} ${idx || ex} 替换为 ${op.exercise}`
    case 'reorder_exercise': return `${day} 第${Number(op.from) + 1}位 ↔ 第${Number(op.to) + 1}位`
    case 'edit_set_prescription': {
      const parts = ['sets', 'reps', 'weight_kg', 'note']
        .filter((k) => op[k] !== undefined).map((k) => `${k}=${op[k]}`)
      return `${day} ${idx} 处方：${parts.join('，')}`
    }
    case 'rename_day': return `${day} 改名 ${op.new_name}`
    case 'set_dimension': {
      const v = op.value as Record<string, unknown> | undefined
      return `训练方式·${op.dimension}：${v ? JSON.stringify(v.value ?? v) : ''}`
    }
    case 'upsert_exercise_choice': return `动作选择 ${op.exercise_id}`
    case 'remove_exercise_choice': return `移除动作选择 ${op.exercise_id}`
    case 'upsert_execution_choice': return `执行选择 ${op.exercise_id}`
    default: return JSON.stringify(op).slice(0, 60)
  }
}

export default function Coach() {
  const uid = useApp((s) => s.uid)
  const navigate = useNavigate()
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [proposals, setProposals] = useState<Proposal[] | null>(null)
  const [consultations, setConsultations] = useState<Consultation[] | null>(null)
  const [proposalNote, setProposalNote] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadProposals = useCallback(() => {
    api.changes(uid).then((r) =>
      setProposals(r.proposals.filter((p) => p.status === 'pending' && p.source === 'ai')))
      .catch(() => setProposals([]))
    api.consultations(uid).then((r) => setConsultations(r.consultations))
      .catch(() => setConsultations([]))
  }, [uid])
  useEffect(() => { loadProposals() }, [loadProposals])
  useEffect(() => { bottomRef.current?.scrollIntoView() }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setSending(true); setError('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    try {
      const r = await api.chat(uid, text)
      setMessages((m) => [...m, { role: 'assistant', content: r.reply }])
      loadProposals() // AI 可能生成了新的待确认修改
    } catch (e) {
      setError((e as ApiError).message)
    } finally { setSending(false) }
  }

  const confirm = async (p: Proposal, accept: boolean) => {
    setProposalNote('')
    const message = accept ? `同意 ${p.id} 这条修改` : '不同意，先不改'
    try {
      const r = await api.confirmChange(uid, p.id, message)
      setProposalNote(r.status === 'applied' ? '已确认并生效 ✓'
        : r.status === 'rejected' ? '已拒绝，该提案关闭'
        : r.note || '表述含糊，提案保持待确认')
      loadProposals()
    } catch (e) {
      setProposalNote((e as ApiError).message)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col pt-4">
      <PageHeader title="AI 教练"
        sub="可以讨论方案、解读记录、提出修改建议——AI 的修改需要你确认才生效" />

      {proposals === null ? <Spinner label="" /> : proposals.length > 0 && (
        <div className="mb-3 space-y-2">
          {proposals.map((p) => (
            <Card key={p.id}
                  title={<span><Tag tone="blue">AI 建议</Tag> <span className="ml-1">{p.target === 'plan' ? '计划修改' : '训练方式调整'}</span></span>}>
              <p className="text-sm text-neutral-300">{p.reason}</p>
              <ul className="mt-1.5 space-y-0.5 text-xs text-neutral-400">
                {(p.operations || []).map((op, i) => (
                  <li key={i}>· {opSummary(op)}</li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-neutral-500">{p.id.slice(0, 12)}… · {p.created_at.slice(0, 10)}</p>
              <div className="mt-2 flex gap-2">
                <button className="btn-primary flex-1 !py-2" onClick={() => confirm(p, true)}>同意</button>
                <button className="btn-danger flex-1 !py-2" onClick={() => confirm(p, false)}>先不改</button>
              </div>
            </Card>
          ))}
          {proposalNote && <p className="text-center text-xs text-accent">{proposalNote}</p>}
        </div>
      )}

      {consultations && consultations.length > 0 && (
        <div className="card mb-2 text-xs">
          <p className="mb-1 font-semibold text-neutral-300">最近咨询的专家</p>
          {consultations.slice(0, 2).map((c) => (
            <div key={c.id} className="mb-1.5 text-neutral-400">
              <p className="truncate">「{c.question}」</p>
              <p className="text-neutral-500">
                {c.advices.map((a) => a.label).join('、')}
                {c.advices.some((a) => a.options.length > 0)
                  ? ` · ${c.advices.reduce((n, a) => n + a.options.length, 0)} 个候选方案` : ''}
              </p>
            </div>
          ))}
          {consultations[0] && consultations[0].advices.flatMap((a) => a.options).length > 0 && (
            <details className="mt-1">
              <summary className="cursor-pointer text-accent">把某个方案变成一次尝试 →</summary>
              <ul className="mt-1 space-y-1">
                {consultations[0].advices.flatMap((a) => a.options.map((o) => ({ label: a.label, o })))
                  .slice(0, 4).map(({ label, o }, i) => (
                  <li key={i}>
                    <button className="text-left text-xs text-neutral-300 underline"
                            onClick={() => {
                              localStorage.setItem('m5-trial-draft', JSON.stringify({
                                change_desc: o.title,
                                reason: `来自${label}建议：${o.detail}`.slice(0, 180),
                              }))
                              navigate('/mine')
                            }}>
                      · {o.title}（{label}）
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      <div className="flex-1 space-y-3 pb-4">
        {messages.length === 0 && (
          <div className="card text-sm leading-relaxed text-neutral-400">
            <p>试试问我：</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-neutral-500">
              <li>最近卧推没进步怎么办</li>
              <li>我想改成上下肢分化，有什么取舍</li>
              <li>总结一下我这两周练得怎么样</li>
            </ul>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : ''}>
            <div className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-left text-sm leading-relaxed ${
              m.role === 'user' ? 'bg-accent/90 text-neutral-950' : 'card'}`}>
              {m.content}
            </div>
          </div>
        ))}
        {error && <ErrorBox message={error} />}
        <div ref={bottomRef} />
      </div>

      <div className="sticky bottom-16 flex gap-2 py-2">
        <input className="input" value={input} placeholder="和教练聊聊…"
               onChange={(e) => setInput(e.target.value)}
               onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send()} />
        <button className="btn-primary shrink-0" disabled={sending || !input.trim()} onClick={send}>
          {sending ? '…' : '发送'}
        </button>
      </div>
    </div>
  )
}
