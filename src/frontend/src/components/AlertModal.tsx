import { useEffect, useMemo } from 'react'
import { theme } from '../theme'

export type AlertKind = 'run' | 'ok' | 'error' | 'warn'

function kindMeta(kind: AlertKind) {
  switch (kind) {
    case 'run':
      return {
        label: '실행 확인',
        icon: '▶',
        accent: theme.primaryBright,
        pillBg: 'rgba(79, 70, 229, 0.12)',
        pillBorder: 'rgba(79, 70, 229, 0.28)',
      }
    case 'error':
      return {
        label: '오류',
        icon: '⚠',
        accent: theme.negative,
        pillBg: theme.negativeBg,
        pillBorder: 'rgba(225, 29, 72, 0.25)',
      }
    case 'warn':
      return {
        label: '주의',
        icon: '!',
        accent: '#f59e0b',
        pillBg: 'rgba(245, 158, 11, 0.12)',
        pillBorder: 'rgba(245, 158, 11, 0.25)',
      }
    case 'ok':
    default:
      return {
        label: '완료되었습니다.',
        icon: '✓',
        accent: theme.positive,
        pillBg: theme.positiveBg,
        pillBorder: 'rgba(16, 185, 129, 0.25)',
      }
  }
}

export default function AlertModal({
  open,
  kind,
  title,
  message,
  yesText,
  noText,
  onYes,
  onNo,
  onClose,
}: {
  open: boolean
  kind: AlertKind
  title?: string
  message: string
  yesText?: string
  noText?: string
  onYes: () => void
  onNo?: () => void
  onClose: () => void
}) {
  const meta = useMemo(() => kindMeta(kind), [kind])
  const hasNo = kind === 'run'
  const primaryLabel = yesText ?? (kind === 'run' ? '예' : '확인')
  const secondaryLabel = noText ?? '아니오'

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Enter') onYes()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose, onYes])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'grid',
        placeItems: 'center',
        padding: 18,
        background: 'rgba(2, 6, 23, 0.55)',
        backdropFilter: 'blur(10px)',
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        style={{
          width: 'min(520px, 94vw)',
          borderRadius: theme.radiusLg,
          overflow: 'hidden',
          border: '1px solid rgba(148, 163, 184, 0.18)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.45)',
          background: 'rgba(15, 23, 42, 0.78)',
          maxHeight: 'min(72vh, 560px)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            padding: '12px 14px',
            background: theme.primary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <div
              aria-hidden
              style={{
                width: 32,
                height: 32,
                borderRadius: 12,
                display: 'grid',
                placeItems: 'center',
                background: 'rgba(255, 255, 255, 0.14)',
                border: '1px solid rgba(255, 255, 255, 0.18)',
                color: '#fff',
                fontWeight: 900,
              }}
            >
              {meta.icon}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontFamily: theme.fontDisplay, fontSize: 14, fontWeight: 900, color: '#fff', letterSpacing: '-0.02em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {title ?? meta.label}
              </div>
              <div
                style={{
                  marginTop: 2,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 10px',
                  borderRadius: 999,
                  background: meta.pillBg,
                  border: `1px solid ${meta.pillBorder}`,
                  color: '#fff',
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                }}
              >
                {kind}
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              width: 34,
              height: 34,
              borderRadius: 12,
              border: '1px solid rgba(255, 255, 255, 0.18)',
              background: 'rgba(255, 255, 255, 0.14)',
              color: '#fff',
              fontSize: 16,
              fontWeight: 900,
              cursor: 'pointer',
            }}
            aria-label="닫기"
            title="닫기 (Esc)"
          >
            ×
          </button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16, minHeight: 0 }}>
          <div
            style={{
              color: '#e2e8f0',
              fontSize: 14,
              lineHeight: 1.55,
              whiteSpace: 'pre-wrap',
              fontFamily: theme.fontSans,
              overflow: 'auto',
              minHeight: 0,
              maxHeight: '42vh',
              paddingRight: 6, // scrollbar 여백
            }}
          >
            {message}
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            {hasNo && (
              <button
                type="button"
                onClick={onNo ?? onClose}
                style={{
                  padding: '10px 14px',
                  borderRadius: 12,
                  border: '1px solid rgba(148, 163, 184, 0.26)',
                  background: 'rgba(148, 163, 184, 0.12)',
                  color: '#e2e8f0',
                  fontWeight: 800,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                {secondaryLabel}
              </button>
            )}
            <button
              type="button"
              onClick={onYes}
              style={{
                padding: '10px 14px',
                borderRadius: 12,
                border: `1px solid ${meta.pillBorder}`,
                background: meta.accent,
                color: '#fff',
                fontWeight: 900,
                fontSize: 13,
                cursor: 'pointer',
                boxShadow: `0 14px 34px -18px ${meta.accent}`,
              }}
            >
              {primaryLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

