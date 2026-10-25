import { useState } from 'react'

type Side = 'left' | 'right'

/** 人体区域选择图（SVG 简化人形；正/背面；左右区域独立点击） */
export default function BodyMap({ view, selected, onToggle }: {
  view: 'front' | 'back'
  selected: string[]            // 形如 "knee:left"
  onToggle: (key: string) => void
}) {
  const isSel = (region: string, side: Side) => selected.includes(`${region}:${side}`)
  const Hotspot = ({ region, side, cx, cy, rx, ry, label }:
    { region: string; side: Side; cx: number; cy: number; rx: number; ry: number
      label: string }) => {
    const sel = isSel(region, side)
    return (
      <g onClick={() => onToggle(`${region}:${side}`)} role="button"
         aria-label={`${label}（${side === 'left' ? '左' : '右'}）`}
         className="cursor-pointer">
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry}
                 fill={sel ? '#3D5A26' : '#A3DD57'} fillOpacity={sel ? 0.9 : 0.45}
                 stroke={sel ? '#2C421B' : '#7FB843'} strokeWidth={sel ? 2 : 1} />
        {sel && (
          <text x={cx} y={cy + 3.5} textAnchor="middle" fontSize="10"
                fill="white" fontWeight="bold">✓</text>
        )}
      </g>
    )
  }

  const midX = 60
  const L = midX - 16
  const R = midX + 16
  return (
    <svg viewBox="0 0 120 220" className="mx-auto h-64" role="img"
         aria-label={view === 'front' ? '正面人体图' : '背面人体图'}>
      {/* 头 */}
      <circle cx={midX} cy={16} r={11} fill="#E8F2DC" stroke="#7FB843" />
      {/* 躯干 */}
      <path d={`M${midX - 14} 30 L${midX + 14} 30 L${midX + 11} 105 L${midX - 11} 105 Z`}
            fill="#E8F2DC" stroke="#7FB843" />
      {/* 手臂 */}
      <line x1={midX - 14} y1={34} x2={L - 6} y2={78} stroke="#7FB843" strokeWidth={7}
            strokeLinecap="round" />
      <line x1={midX + 14} y1={34} x2={R + 6} y2={78} stroke="#7FB843" strokeWidth={7}
            strokeLinecap="round" />
      <line x1={L - 6} y1={78} x2={L - 8} y2={116} stroke="#7FB843" strokeWidth={6}
            strokeLinecap="round" />
      <line x1={R + 6} y1={78} x2={R + 8} y2={116} stroke="#7FB843" strokeWidth={6}
            strokeLinecap="round" />
      {/* 腿 */}
      <line x1={midX - 7} y1={105} x2={L - 2} y2={160} stroke="#7FB843" strokeWidth={9}
            strokeLinecap="round" />
      <line x1={midX + 7} y1={105} x2={R + 2} y2={160} stroke="#7FB843" strokeWidth={9}
            strokeLinecap="round" />
      <line x1={L - 2} y1={160} x2={L - 2} y2={200} stroke="#7FB843" strokeWidth={8}
            strokeLinecap="round" />
      <line x1={R + 2} y1={160} x2={R + 2} y2={200} stroke="#7FB843" strokeWidth={8}
            strokeLinecap="round" />
      {/* 背面专属：腰背 */}
      {view === 'back' && (
        <>
          <rect x={midX - 7} y={62} width={14} height={38} rx={6}
                fill="#A3DD57" fillOpacity={0.45} stroke="#7FB843" />
          <Hotspot region="lower_back" side="left" cx={midX - 4} cy={80} rx={5} ry={15} label="腰背左" />
          <Hotspot region="lower_back" side="right" cx={midX + 4} cy={80} rx={5} ry={15} label="腰背右" />
          <text x={midX} y={56} textAnchor="middle" fontSize="7" fill="#5A6B4F">腰背</text>
        </>
      )}
      {view === 'front' && (
        <text x={midX} y={110} textAnchor="middle" fontSize="7" fill="#98A49C">正面</text>
      )}
      {/* 颈 */}
      <Hotspot region="neck" side="left" cx={midX - 3} cy={27} rx={4} ry={3} label="颈左" />
      <Hotspot region="neck" side="right" cx={midX + 3} cy={27} rx={4} ry={3} label="颈右" />
      {/* 肩 */}
      <Hotspot region="shoulder" side="left" cx={midX - 12} cy={33} rx={5} ry={4} label="肩左" />
      <Hotspot region="shoulder" side="right" cx={midX + 12} cy={33} rx={5} ry={4} label="肩右" />
      {/* 肘 */}
      <Hotspot region="elbow" side="left" cx={L - 6} cy={78} rx={4.5} ry={4.5} label="肘左" />
      <Hotspot region="elbow" side="right" cx={R + 6} cy={78} rx={4.5} ry={4.5} label="肘右" />
      {/* 腕 */}
      <Hotspot region="wrist" side="left" cx={L - 8} cy={114} rx={4} ry={4} label="腕左" />
      <Hotspot region="wrist" side="right" cx={R + 8} cy={114} rx={4} ry={4} label="腕右" />
      {/* 髋 */}
      <Hotspot region="hip" side="left" cx={midX - 8} cy={102} rx={5} ry={4.5} label="髋左" />
      <Hotspot region="hip" side="right" cx={midX + 8} cy={102} rx={5} ry={4.5} label="髋右" />
      {/* 膝 */}
      <Hotspot region="knee" side="left" cx={L - 2} cy={160} rx={5.5} ry={5} label="膝左" />
      <Hotspot region="knee" side="right" cx={R + 2} cy={160} rx={5.5} ry={5} label="膝右" />
      {/* 踝 */}
      <Hotspot region="ankle" side="left" cx={L - 2} cy={198} rx={4.5} ry={4} label="踝左" />
      <Hotspot region="ankle" side="right" cx={R + 2} cy={198} rx={4.5} ry={4} label="踝右" />
    </svg>
  )
}

/** 已选区域解析为 {region, side} 列表 */
export function parseSelection(selected: string[]):
  { region: string; side: 'left' | 'right' }[] {
  return selected.map((s) => {
    const [region, side] = s.split(':')
    return { region, side: side as 'left' | 'right' }
  })
}

export function useBodyMapView() {
  return useState<'front' | 'back'>('front')
}
