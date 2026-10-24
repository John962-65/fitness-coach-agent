import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { Card, ErrorBox, PageHeader, Spinner, Tag } from '../components/Bits'
import { useApp } from '../store'
import { ChatMsg, Proposal } from '../types'

export default function Coach() {
  const uid = useApp((s) => s.uid)
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [proposals, setProposals] = useState<Proposal[] | null>(null)
  const [proposalNote, setProposalNote] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadProposals = useCallback(() => {
    api.changes(uid).then((r) =>
      setProposals(r.proposals.filter((p) => p.status === 'pending' && p.source === 'ai')))
      .catch(() => setProposals([]))
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
