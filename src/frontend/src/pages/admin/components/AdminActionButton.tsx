import type { CSSProperties, ReactNode } from 'react'
import { theme } from '../../../theme'

export default function AdminActionButton({
  title,
  subtitle,
  tone = 'neutral',
  onClick,
  right,
  disabled,
}: {
  title: string
  subtitle?: string
  tone?: 'neutral' | 'danger' | 'success' | 'warning'
  onClick: () => void
  right?: ReactNode
  disabled?: boolean
}) {
  const border =
    tone === 'danger'
      ? 'rgba(239, 68, 68, 0.35)'
      : tone === 'success'
        ? 'rgba(16, 185, 129, 0.28)'
        : tone === 'warning'
          ? 'rgba(245, 158, 11, 0.42)'
          : theme.outline

  const bg =
    tone === 'danger'
      ? 'linear-gradient(180deg, rgba(239, 68, 68, 0.14) 0%, rgba(255, 255, 255, 0.04) 100%)'
      : tone === 'success'
        ? 'linear-gradient(180deg, rgba(16, 185, 129, 0.12) 0%, rgba(255, 255, 255, 0.04) 100%)'
        : tone === 'warning'
          ? 'linear-gradient(180deg, rgba(245, 158, 11, 0.14) 0%, rgba(255, 255, 255, 0.04) 100%)'
          : 'linear-gradient(180deg, rgba(79, 70, 229, 0.10) 0%, rgba(255, 255, 255, 0.04) 100%)'

  const btn: CSSProperties = {
    width: '100%',
    textAlign: 'left',
    appearance: 'none',
    borderRadius: theme.radiusLg,
    border: `1px solid ${border}`,
    background: bg,
    padding: 14,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    transition: 'transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease',
    boxShadow: theme.shadow,
  }

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={btn}
      onMouseDown={(e) => {
        if (disabled) return
        ;(e.currentTarget as HTMLButtonElement).style.transform = 'translateY(1px)'
      }}
      onMouseUp={(e) => {
        ;(e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0px)'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 900, color: theme.onSurface, letterSpacing: '-0.01em' }}>
            {title}
          </div>
          {subtitle && (
            <div style={{ marginTop: 6, fontSize: 12, color: theme.onSurfaceVariant, lineHeight: 1.35 }}>
              {subtitle}
            </div>
          )}
        </div>
        {right && <div style={{ flexShrink: 0 }}>{right}</div>}
      </div>
    </button>
  )
}

