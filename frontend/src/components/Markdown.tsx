// 安全 Markdown 渲染器（M6.2 P1）：教学文档与 AI 教练回复共用。
// 解析（parseBlocks/parseInline，纯函数可测）与渲染分离；
// 全部内容经 React 子元素输出，绝不使用 dangerouslySetInnerHTML。
import { ReactNode, useMemo } from 'react'

export type Inline = { t: 'text' | 'bold' | 'code'; v: string }

export type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'quote'; lines: string[] }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'table'; header: string[]; rows: string[][] }
  | { type: 'hr' }
  | { type: 'p'; text: string }

const HEADING_RE = /^#{1,4}\s+/
const HR_RE = /^(?:---+|\*\*\*+)\s*$/
const UL_RE = /^[-*]\s+/
const OL_RE = /^(?:\d{1,2}、|\d{1,2}[.)]\s)\s*/
const TABLE_SEP_RE = /^\|[\s:|-]+\|?$/

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  const re = /\*\*([^*]+)\*\*|`([^`\n]+)`/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push({ t: 'text', v: text.slice(last, m.index) })
    if (m[1] !== undefined) out.push({ t: 'bold', v: m[1] })
    else out.push({ t: 'code', v: m[2] as string })
    last = re.lastIndex
  }
  if (last < text.length) out.push({ t: 'text', v: text.slice(last) })
  return out
}

const parseRow = (line: string): string[] =>
  line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())

export function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const t = line.trim()
    if (!t) { i++; continue }
    if (HEADING_RE.test(t)) {
      blocks.push({ type: 'heading', level: (t.match(/^#+/) as RegExpMatchArray)[0].length,
                    text: t.replace(HEADING_RE, '') })
      i++; continue
    }
    if (HR_RE.test(t)) { blocks.push({ type: 'hr' }); i++; continue }
    if (t.startsWith('>')) {
      const ls: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        ls.push(lines[i].trim().replace(/^>\s?/, '')); i++
      }
      blocks.push({ type: 'quote', lines: ls }); continue
    }
    if (t.startsWith('|') && i + 1 < lines.length && TABLE_SEP_RE.test(lines[i + 1].trim())) {
      const header = parseRow(t)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith('|')) { rows.push(parseRow(lines[i])); i++ }
      blocks.push({ type: 'table', header, rows }); continue
    }
    if (UL_RE.test(t)) {
      const items: string[] = []
      while (i < lines.length && UL_RE.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(UL_RE, '')); i++
      }
      blocks.push({ type: 'ul', items }); continue
    }
    if (OL_RE.test(t)) {
      const items: string[] = []
      while (i < lines.length && OL_RE.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(OL_RE, '')); i++
      }
      blocks.push({ type: 'ol', items }); continue
    }
    // 段落：连续普通行合并（保留换行，中文排版常见硬换行）。
    // 注意：`|` 行只有在其下一行是分隔行时才可能是表格——否则必须并入段落，
    // 否则该行永远无法被消费（死循环）。
    const pl: string[] = []
    while (i < lines.length) {
      const lt = lines[i].trim()
      const tableAhead = lt.startsWith('|') && i + 1 < lines.length
        && TABLE_SEP_RE.test(lines[i + 1].trim())
      if (!lt || HEADING_RE.test(lt) || HR_RE.test(lt) || UL_RE.test(lt) || OL_RE.test(lt)
          || lt.startsWith('>') || tableAhead) break
      pl.push(lt); i++
    }
    if (pl.length) blocks.push({ type: 'p', text: pl.join('\n') })
  }
  return blocks
}

function renderInline(text: string, key: string): ReactNode[] {
  return parseInline(text).map((tok, i) =>
    tok.t === 'bold' ? <strong key={`${key}-${i}`} className="font-semibold text-ink">{tok.v}</strong>
    : tok.t === 'code' ? <code key={`${key}-${i}`} className="nums rounded bg-canvas px-1 py-0.5
                                    font-mono text-[13px] text-ink">{tok.v}</code>
    : <span key={`${key}-${i}`}>{tok.v}</span>)
}

export function Markdown({ text, className = '' }: { text: string; className?: string }) {
  const blocks = useMemo(() => parseBlocks(text), [text])
  return (
    <div className={`space-y-2 text-sm leading-relaxed text-ink/90 ${className}`}>
      {blocks.map((b, i) => {
        const key = `b${i}`
        switch (b.type) {
          case 'heading':
            return b.level <= 1
              ? <h3 key={key} className="pb-1 text-[15px] font-bold text-ink">{renderInline(b.text, key)}</h3>
              : b.level === 2
                ? <h4 key={key} className="pt-1 text-sm font-semibold text-ink">{renderInline(b.text, key)}</h4>
                : <h5 key={key} className="pt-0.5 text-[13px] font-semibold text-muted">{renderInline(b.text, key)}</h5>
          case 'quote':
            return (
              <blockquote key={key}
                          className="rounded-r-lg border-l-4 border-accent/60 bg-accent-soft/60 px-3 py-2
                                     font-medium text-accent-deep">
                {b.lines.map((l, j) => <p key={j}>{renderInline(l, `${key}-${j}`)}</p>)}
              </blockquote>
            )
          case 'ul':
            return (
              <ul key={key} className="space-y-1">
                {b.items.map((it, j) => (
                  <li key={j} className="flex gap-2">
                    <span className="mt-[7px] size-1.5 shrink-0 rounded-full bg-lineStrong" aria-hidden />
                    <span>{renderInline(it, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={key} className="space-y-1">
                {b.items.map((it, j) => (
                  <li key={j} className="flex gap-2">
                    <span className="nums shrink-0 font-semibold text-accent-deep">{j + 1}.</span>
                    <span>{renderInline(it, `${key}-${j}`)}</span>
                  </li>
                ))}
              </ol>
            )
          case 'table':
            return (
              <div key={key} className="overflow-x-auto rounded-xl border border-line">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="bg-canvas">
                      {b.header.map((h, j) => (
                        <th key={j} className="px-2.5 py-1.5 text-left font-semibold text-ink">
                          {renderInline(h, `${key}-h${j}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j} className="border-t border-line">
                        {r.map((c, k) => (
                          <td key={k} className="px-2.5 py-1.5 align-top">{renderInline(c, `${key}-${j}-${k}`)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'hr':
            return <hr key={key} className="border-line" />
          case 'p':
          default:
            return <p key={key} className="whitespace-pre-wrap">{renderInline(b.text, key)}</p>
        }
      })}
    </div>
  )
}
