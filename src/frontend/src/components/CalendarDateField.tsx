import type { CSSProperties } from 'react'
import { useId, useRef } from 'react'
import { theme } from '../theme'

const shell: CSSProperties = {
  position: 'relative',
  display: 'inline-flex',
  alignItems: 'center',
  minWidth: 152,
  minHeight: 40,
  padding: '0 12px',
  borderRadius: theme.radiusMd,
  border: `1px solid ${theme.outline}`,
  background: theme.surface,
  cursor: 'pointer',
  fontFamily: theme.fontSans,
  fontSize: 13,
  fontWeight: 600,
  color: theme.onSurface,
  gap: 8,
}

export default function CalendarDateField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (ymd: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const id = useId()

  const openPicker = () => {
    const el = inputRef.current
    if (!el) return
    const anyEl = el as HTMLInputElement & { showPicker?: () => void }
    if (typeof anyEl.showPicker === 'function') {
      try {
        anyEl.showPicker()
        return
      } catch {
        /* 일부 브라우저에서 사용자 제스처 외 호출 시 실패 */
      }
    }
    el.focus()
    el.click()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 12, color: theme.onSurfaceVariant }} id={`${id}-l`}>
        {label}
      </span>
      <div
        role="button"
        tabIndex={0}
        aria-labelledby={`${id}-l`}
        aria-haspopup="dialog"
        className="trader-btn"
        style={shell}
        onClick={openPicker}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            openPicker()
          }
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden style={{ flexShrink: 0, opacity: 0.75 }}>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
        <span style={{ fontVariantNumeric: 'tabular-nums' }}>{value}</span>
        <input
          ref={inputRef}
          id={id}
          type="date"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-label={label}
          tabIndex={-1}
          style={{
            position: 'absolute',
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: 'hidden',
            clip: 'rect(0,0,0,0)',
            whiteSpace: 'nowrap',
            border: 0,
            opacity: 0,
            pointerEvents: 'none',
          }}
        />
      </div>
    </div>
  )
}
