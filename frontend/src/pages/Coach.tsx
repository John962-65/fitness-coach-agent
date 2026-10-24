import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BadgeCheck, FileText, FlaskConical, Send, Sparkles, Stethoscope, UserRound,
} from 'lucide-react'
import { api, ApiError } from '../api'
import {
  Button, Empty, ErrorBox, PlainButton, Spinner, Tag,
} from '../components/Bits'
import { Markdown } from '../components/Markdown'
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

const SUGGESTIONS = [
  '最近卧推没进步怎么办',
  '我想改成上下肢分化，有什么取舍',
  '总结一下我这两周练得怎么样',
]

type Tab = 'chat' | 'proposals' | 'consult'

export default function Coach() {
  const uid = useApp((s) => s.uid)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [proposals, setProposals] = useState<Proposal[] | null>(null)
  const [consultations, setConsultations] = useState<Consultation[] | null>(null)
  const [proposalNote, setProposalNote] = useState('')
  const [tab, setTab] = useState<Tab>('chat')
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadProposals = useCallback(() => {
    api.changes(uid).then((r) =>
      setProposals(r.proposals.filter((p) => p.status === 'pending' && p.source === 'ai')))
      .catch(() => setProposals([]))
    api.consultations(uid).then((r) => setConsultations(r.consultations))
      .catch(() => setConsultations([]))
  }, [uid])
  useEffect(() => { loadProposals() }, [loadProposals])
  useEffect(() => { bottomRef.current?.scrollIntoView() }, [messages, sending])

  const send = async (textArg?: string) => {
    const text = (textArg ?? input).trim()
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

  const pendingCount = proposals?.length ?? 0
  const chatColumn = (onMobile: boolean) => (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4 lg:px-6">
        {messages.length === 0 && !sending && (
          <div className="mx-auto max-w-md pt-6">
            <div className="flex flex-col items-center gap-2 text-center">
              <span className="flex size-12 items-center justify-center rounded-2xl bg-accent-soft">
                <Sparkles size={22} className="text-accent-deep" />
              </span>
              <p className="mt-1 text-lg font-bold">和你的 AI 教练聊聊</p>
              <p className="text-[13px] leading-relaxed text-muted">
                可以讨论方案、解读记录、提出修改建议——AI 的修改需要你确认才生效。
              </p>
            </div>
            <div className="mt-5 space-y-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => onMobile ? setInput(s) : send(s)}
                        className="btn-ghost w-full justify-start !justify-start text-left font-normal text-muted">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2.5 animate-fade-up ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && (
              <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-night">
                <Sparkles size={13} className="text-accent" />
              </span>
            )}
            <div className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-left text-sm leading-relaxed ${
              m.role === 'user'
                ? 'rounded-br-md bg-accent font-medium text-ink'
                : 'rounded-tl-md border border-line bg-surface shadow-card'}`}>
              {m.role === 'user'
                ? <span className="whitespace-pre-wrap">{m.content}</span>
                : <Markdown text={m.content} />}
            </div>
            {m.role === 'user' && (
              <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-canvas text-muted">
                <UserRound size={14} />
              </span>
            )}
          </div>
        ))}
        {sending && (
          <div className="flex gap-2.5">
            <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-night">
              <Sparkles size={13} className="text-accent" />
            </span>
            <div className="flex items-center gap-1.5 rounded-2xl rounded-tl-md border border-line bg-surface px-4 py-3">
              <span className="size-1.5 animate-pulse-soft rounded-full bg-muted" />
              <span className="size-1.5 animate-pulse-soft rounded-full bg-muted [animation-delay:0.3s]" />
              <span className="size-1.5 animate-pulse-soft rounded-full bg-muted [animation-delay:0.6s]" />
            </div>
          </div>
        )}
        {error && <ErrorBox message={error} />}
        <div ref={bottomRef} />
      </div>

      {/* 输入区（吸底；移动端在底部导航之上） */}
      {onMobile ? (
        <div className="border-t border-line bg-surface px-4 py-3"
             style={{ paddingBottom: 'max(12px, calc(env(safe-area-inset-bottom) + 12px))' }}>
          <div className="flex items-end gap-2">
            <textarea className="input max-h-32 min-h-11 flex-1 resize-none py-2.5" rows={1}
                      value={input} placeholder="和教练聊聊…"
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn-primary size-11 shrink-0 !px-0" disabled={sending || !input.trim()}
                    onClick={() => send()} aria-label="发送">
              <Send size={17} />
            </button>
          </div>
        </div>
      ) : (
        <div className="border-t border-line bg-surface px-6 py-3">
          <div className="flex items-end gap-2">
            <textarea className="input max-h-32 min-h-11 flex-1 resize-none py-2.5" rows={1}
                      value={input} placeholder="和教练聊聊…（Enter 发送，Shift+Enter 换行）"
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn-primary size-11 shrink-0 !px-0" disabled={sending || !input.trim()}
                    onClick={() => send()} aria-label="发送">
              <Send size={17} />
            </button>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="flex h-[calc(100dvh-3.5rem-env(safe-area-inset-bottom))] flex-col lg:h-dvh">
      {/* 页头 + 移动端分栏 Tabs（对话与提案/咨询分离） */}
      <div className="border-b border-line bg-canvas px-4 pb-2.5 pt-3 lg:hidden">
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold">AI 教练</h1>
          <Tag tone="brand"><Sparkles size={11} /> 修改需你确认</Tag>
        </div>
        <div className="mt-2.5 flex gap-1 rounded-xl bg-ink/5 p-1" role="tablist">
          {([
            ['chat', '对话'],
            ['proposals', '待确认修改', pendingCount],
            ['consult', '专家咨询'],
          ] as const).map(([v, label, badge]) => (
            <button key={v} role="tab" aria-selected={tab === v}
                    onClick={() => setTab(v as Tab)}
                    className={`relative flex min-h-[38px] flex-1 items-center justify-center gap-1.5 rounded-lg
                                px-2 text-[13px] font-medium transition-all ${
                                  tab === v ? 'bg-surface text-ink shadow-card' : 'text-muted'}`}>
              {label}
              {badge != null && badge > 0 && (
                <span className="nums flex h-[18px] min-w-[18px] items-center justify-center rounded-full
                                 bg-accent px-1 text-[11px] font-bold text-ink">{badge}</span>
              )}
            </button>
          ))}
        </div>
      </div>
      {/* 桌面页头 */}
      <div className="hidden items-center justify-between border-b border-line px-6 py-4 lg:flex">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">AI 教练</h1>
          <p className="mt-0.5 text-[13px] text-muted">
            讨论方案 · 解读记录 · 提出修改建议——修改需要你确认才生效
          </p>
        </div>
      </div>

      {/* 移动端：按 Tab 切换 */}
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        {tab === 'chat' && chatColumn(true)}
        {tab === 'proposals' && (
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {proposalNote && (
              <p className="rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
                {proposalNote}
              </p>
            )}
            <ProposalsList proposals={proposals} onConfirm={confirm} />
          </div>
        )}
        {tab === 'consult' && (
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
            <ConsultList consultations={consultations} />
          </div>
        )}
      </div>

      {/* 桌面端：左对话 + 右侧栏（提案/咨询常驻） */}
      <div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-[1fr,380px]">
        {chatColumn(false)}
        <aside className="flex min-h-0 flex-col border-l border-line">
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {proposalNote && (
              <p className="rounded-xl bg-accent-soft px-3.5 py-2.5 text-center text-[13px] text-accent-deep">
                {proposalNote}
              </p>
            )}
            <h2 className="flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide text-muted">
              <FileText size={13} /> 待确认修改（{pendingCount}）
            </h2>
            <ProposalsList proposals={proposals} onConfirm={confirm} />
            <h2 className="mt-4 flex items-center gap-1.5 border-t border-line pt-4 text-[13px]
                           font-semibold uppercase tracking-wide text-muted">
              <Stethoscope size={13} /> 专家咨询
            </h2>
            <ConsultList consultations={consultations} compact />
          </div>
        </aside>
      </div>
    </div>
  )
}

/* ---------------- 待确认修改提案卡 ---------------- */

function ProposalsList({ proposals, onConfirm }: {
  proposals: Proposal[] | null
  onConfirm: (p: Proposal, accept: boolean) => void
}) {
  if (proposals === null) return <Spinner label="" />
  if (proposals.length === 0) {
    return (
      <Empty icon={<BadgeCheck size={20} />} title="没有待确认的修改">
        AI 的一切修改都会先列在这里，经你确认才生效。
      </Empty>
    )
  }
  return (
    <>
      {proposals.map((p) => (
        <div key={p.id} className="card border-accent/40">
          <div className="mb-2 flex items-center justify-between gap-2">
            <Tag tone="brand"><Sparkles size={11} /> AI 建议 · {p.target === 'plan' ? '计划修改' : '训练方式调整'}</Tag>
            <span className="text-2xs text-faint">{p.created_at.slice(0, 10)}</span>
          </div>
          <p className="text-sm leading-relaxed">{p.reason}</p>
          {(p.operations || []).length > 0 && (
            <div className="mt-2.5 rounded-xl bg-canvas p-3">
              <p className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">修改内容</p>
              <ul className="space-y-1">
                {(p.operations || []).map((op, i) => (
                  <li key={i} className="text-[13px] leading-relaxed text-ink">· {opSummary(op)}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-2 text-2xs leading-relaxed text-faint">
            影响范围：{p.target === 'plan' ? '当前训练计划（确认后生成新版本）' : '我的训练方式（确认后记录新版本）'}
            · {p.id.slice(0, 12)}…
          </p>
          <div className="mt-3 flex gap-2">
            <Button className="flex-1 !py-2.5" onClick={() => onConfirm(p, true)}>同意修改</Button>
            <Button variant="ghost" className="flex-1 !py-2.5" onClick={() => onConfirm(p, false)}>先不改</Button>
          </div>
        </div>
      ))}
    </>
  )
}

/* ---------------- 专家咨询历史 ---------------- */

function ConsultList({ consultations, compact }: {
  consultations: Consultation[] | null; compact?: boolean
}) {
  const navigate = useNavigate()
  if (consultations === null) return <Spinner label="" />
  if (consultations.length === 0) {
    return (
      <Empty icon={<Stethoscope size={20} />} title="还没有专家咨询">
        在对话里提出具体问题，教练会转给对应方向的专家给出候选方案。
      </Empty>
    )
  }
  const list = compact ? consultations.slice(0, 3) : consultations
  return (
    <div className="space-y-3">
      {list.map((c) => {
        const options = c.advices.flatMap((a) => a.options.map((o) => ({ label: a.label, o })))
        return (
          <div key={c.id} className="card">
            <p className="text-sm font-medium leading-relaxed">「{c.question}」</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {c.advices.map((a) => <Tag key={a.label} tone="blue">{a.label}</Tag>)}
              {options.length > 0 && <Tag>{options.length} 个候选方案</Tag>}
            </div>
            {options.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-[13px] font-medium text-accent-deep">
                  查看候选方案，可发起尝试
                </summary>
                <ul className="mt-2 space-y-2">
                  {options.slice(0, 6).map(({ label, o }, i) => (
                    <li key={i} className="rounded-xl bg-canvas p-3">
                      <p className="text-[13px] font-medium">{o.title}
                        <span className="ml-1.5 text-2xs text-faint">{label}</span>
                      </p>
                      <p className="mt-0.5 text-xs leading-relaxed text-muted">{o.detail}</p>
                      <PlainButton className="mt-1 !text-accent-deep"
                                   onClick={() => {
                                     localStorage.setItem('m5-trial-draft', JSON.stringify({
                                       change_desc: o.title,
                                       reason: `来自${label}建议：${o.detail}`.slice(0, 180),
                                     }))
                                     navigate('/mine')
                                   }}>
                        <FlaskConical size={13} /> 发起一次尝试
                      </PlainButton>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )
      })}
    </div>
  )
}
