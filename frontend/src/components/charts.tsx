// 轻量 SVG 趋势图（M6.3）：不引入图表库，保持包体与视觉一致。
// 仅做展示：折线 + 数据点 + 首末标签；数值口径由调用方保证（如 e1RM/容量）。
export function Sparkline({ points, unit = '', height = 88 }: {
  points: { label: string; value: number }[]
  unit?: string
  height?: number
}) {
  if (points.length === 0) return null
  const w = 320
  const pad = 10
  const values = points.map((p) => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const x = (i: number) => pad + i * ((w - pad * 2) / Math.max(points.length - 1, 1))
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2 - 14)
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const area = `${path} L${x(points.length - 1).toFixed(1)},${height - pad} L${x(0).toFixed(1)},${height - pad} Z`
  const last = points[points.length - 1]

  return (
    <div>
      <svg viewBox={`0 0 ${w} ${height}`} className="h-auto w-full" role="img"
           aria-label={`趋势图：${points.length} 个数据点`}>
        <path d={area} fill="var(--color-accent, #B8EE70)" opacity="0.18" />
        <path d={path} fill="none" stroke="#3D5A26" strokeWidth="2" strokeLinejoin="round"
              strokeLinecap="round" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={i === points.length - 1 ? 3.5 : 2.5}
                  fill={i === points.length - 1 ? '#3D5A26' : '#A3DD57'} />
        ))}
        <text x={pad} y={12} fontSize="10" fill="#98A49C">
          {points[0].label}
        </text>
        <text x={w - pad} y={12} fontSize="10" fill="#3D5A26" textAnchor="end">
          {last.value}{unit} · {last.label}
        </text>
      </svg>
      <div className="nums flex justify-between text-2xs text-faint">
        <span>最低 {min}{unit}</span>
        <span>最高 {max}{unit}</span>
      </div>
    </div>
  )
}
