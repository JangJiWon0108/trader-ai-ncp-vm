import { theme } from '../theme'

type Variant = 'buy' | 'sell' | 'hold' | 'neutral'

const variantStyle: Record<
  Variant,
  { bg: string; color: string; ring: string; label: string }
> = {
  buy: {
    bg: 'linear-gradient(135deg, rgba(5, 150, 105, 0.2), rgba(16, 185, 129, 0.08))',
    color: '#047857',
    ring: 'rgba(5, 150, 105, 0.35)',
    label: '매수',
  },
  sell: {
    bg: 'linear-gradient(135deg, rgba(225, 29, 72, 0.18), rgba(244, 63, 94, 0.06))',
    color: '#be123c',
    ring: 'rgba(225, 29, 72, 0.35)',
    label: '매도',
  },
  hold: {
    bg: 'rgba(148, 163, 184, 0.15)',
    color: '#475569',
    ring: 'rgba(148, 163, 184, 0.35)',
    label: '보유',
  },
  neutral: {
    bg: 'rgba(79, 70, 229, 0.12)',
    color: theme.primaryBright,
    ring: 'rgba(79, 70, 229, 0.3)',
    label: '',
  },
}

export default function Badge({
  variant,
  children,
}: {
  variant: Variant
  children?: string
}) {
  const v = variantStyle[variant]
  const text = children ?? v.label
  if (!text) return null
  return (
    <span
      className="trader-badge"
      style={{
        display: 'inline-block',
        padding: '5px 12px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        fontVariantNumeric: 'tabular-nums',
        fontFamily: theme.fontSans,
        background: v.bg,
        color: v.color,
        border: `1px solid ${v.ring}`,
        boxShadow: `0 1px 0 rgba(255,255,255,0.6) inset`,
      }}
    >
      {text}
    </span>
  )
}
