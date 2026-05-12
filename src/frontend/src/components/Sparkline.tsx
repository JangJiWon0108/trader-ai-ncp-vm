import { useId } from 'react'
import { theme } from '../theme'

/** Normalized 0–1 heights, left to right */
export default function Sparkline({
  points,
  positive,
}: {
  points: number[]
  /** When set, uses green/red gradient instead of brand violet */
  positive?: boolean
}) {
  const uid = useId().replace(/:/g, '')
  const w = 120
  const h = 36
  const gradId = `sp-${uid}`
  if (points.length < 2)
    return (
      <span className="trader-chart-wrap">
        <div style={{ width: w, height: h }} />
      </span>
    )
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = w / (points.length - 1)
  const d = points
    .map((p, i) => {
      const x = i * step
      const y = h - ((p - min) / span) * (h - 4) - 2
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  const c0 = positive === true ? '#059669' : positive === false ? theme.negative : theme.primaryBright
  const c1 = positive === true ? '#34d399' : positive === false ? '#fda4af' : theme.accentCyan

  return (
    <span className="trader-chart-wrap">
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden>
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={c0} />
            <stop offset="100%" stopColor={c1} />
          </linearGradient>
        </defs>
        <path
          d={d}
          fill="none"
          stroke={`url(#${gradId})`}
          strokeWidth={2.25}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            filter:
              positive === true
                ? 'drop-shadow(0 2px 5px rgba(5, 150, 105, 0.35))'
                : positive === false
                  ? 'drop-shadow(0 2px 5px rgba(225, 29, 72, 0.3))'
                  : 'drop-shadow(0 2px 6px rgba(79, 70, 229, 0.28))',
          }}
        />
      </svg>
    </span>
  )
}
