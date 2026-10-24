// M6.2：Markdown 解析规则锁定（渲染组件基于此，不含 HTML 注入路径）
import { describe, expect, it } from 'vitest'
import { parseBlocks, parseInline } from './Markdown'

describe('parseInline', () => {
  it('加粗与行内代码', () => {
    expect(parseInline('**胸肌主导**，想象`把杠铃掰弯`')).toEqual([
      { t: 'bold', v: '胸肌主导' },
      { t: 'text', v: '，想象' },
      { t: 'code', v: '把杠铃掰弯' },
    ])
  })
  it('纯文本与不成对星号原样保留', () => {
    expect(parseInline('普通文本')).toEqual([{ t: 'text', v: '普通文本' }])
    expect(parseInline('a * b ** c')).toEqual([{ t: 'text', v: 'a * b ** c' }])
  })
})

describe('parseBlocks', () => {
  it('标题层级', () => {
    expect(parseBlocks('# 大标题\n## 小节\n### 细项')).toEqual([
      { type: 'heading', level: 1, text: '大标题' },
      { type: 'heading', level: 2, text: '小节' },
      { type: 'heading', level: 3, text: '细项' },
    ])
  })

  it('表格：表头 + 分隔行 + 数据行', () => {
    const md = '| 错误 | 后果 | 纠正 |\n|------|------|------|\n| 弹胸 | 失去控制 | 停顿 1 秒 |'
    expect(parseBlocks(md)).toEqual([{
      type: 'table',
      header: ['错误', '后果', '纠正'],
      rows: [['弹胸', '失去控制', '停顿 1 秒']],
    }])
  })

  it('引用块与列表', () => {
    const md = '> 卧推不是"推出去"\n> 是"把自己推离杠铃"\n\n- 肩胛骨后缩\n- 脚踩实\n1. 下放\n2. 推起'
    expect(parseBlocks(md)).toEqual([
      { type: 'quote', lines: ['卧推不是"推出去"', '是"把自己推离杠铃"'] },
      { type: 'ul', items: ['肩胛骨后缩', '脚踩实'] },
      { type: 'ol', items: ['下放', '推起'] },
    ])
  })

  it('中文顿号编号列表与分割线', () => {
    const md = '1、第一点\n2、第二点\n\n---'
    expect(parseBlocks(md)).toEqual([
      { type: 'ol', items: ['第一点', '第二点'] },
      { type: 'hr' },
    ])
  })

  it('普通段落保留硬换行；不把表格行误判为段落', () => {
    const md = '第一行\n第二行\n| 已在表格处理后 |'
    expect(parseBlocks(md)).toEqual([
      { type: 'p', text: '第一行\n第二行\n| 已在表格处理后 |' },
    ])
  })

  it('真实教学文档解析稳定（bench_press_technique.md 形状）', () => {
    const md = '# 卧推技术细节\n\n> **卧推不是"推出去"，是"把自己推离杠铃"。**\n\n## 关键细节\n\n### 1. 躺姿\n- **肩胛骨后缩下沉**\n- 脚踏实地面'
    const blocks = parseBlocks(md)
    expect(blocks[0]).toEqual({ type: 'heading', level: 1, text: '卧推技术细节' })
    expect(blocks[1].type).toBe('quote')
    expect(blocks).toContainEqual({ type: 'heading', level: 2, text: '关键细节' })
    expect(blocks).toContainEqual({ type: 'heading', level: 3, text: '1. 躺姿' })
    expect(blocks).toContainEqual({ type: 'ul', items: ['**肩胛骨后缩下沉**', '脚踏实地面'] })
  })
})
