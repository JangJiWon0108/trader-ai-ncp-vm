import { useEffect, useRef } from 'react'
import { theme } from '../../../theme'

const mono =
  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"

export default function LogViewerModal({
  open,
  title = '백엔드 로그',
  subtitle,
  text,
  loading,
  onRefresh,
  onClose,
}: {
  open: boolean
  title?: string
  subtitle?: string
  text: string
  loading?: boolean
  onRefresh?: () => void
  onClose: () => void
}) {
  const preRef = useRef<HTMLPreElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    const el = preRef.current
    if (!el) return
    // 사용자가 위로 스크롤해서 보고 있지 않으면(바닥 근처면) 최신 로그로 자동 스크롤
    const gap = el.scrollHeight - el.scrollTop - el.clientHeight
    const nearBottom = gap < 120
    if (nearBottom) el.scrollTop = el.scrollHeight
  }, [open, text])

  if (!open) return null

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // clipboard 미지원/권한 거부는 무시(UX만 제공)
    }
  }

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
          width: 'min(1200px, 96vw)',
          height: 'min(84vh, 860px)',
          borderRadius: theme.radiusLg,
          overflow: 'hidden',
          border: '1px solid rgba(148, 163, 184, 0.18)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.45)',
          background: 'rgba(15, 23, 42, 0.78)',
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
          <div style={{ minWidth: 0 }}>
            <div
              style={{
                fontFamily: theme.fontDisplay,
                fontSize: 14,
                fontWeight: 900,
                color: '#fff',
                letterSpacing: '-0.02em',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {title}
            </div>
            {subtitle && (
              <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(226,232,240,0.85)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {subtitle}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={loading}
                style={{
                  padding: '8px 12px',
                  borderRadius: 12,
                  border: '1px solid rgba(255, 255, 255, 0.18)',
                  background: 'rgba(255, 255, 255, 0.14)',
                  color: '#fff',
                  fontWeight: 900,
                  fontSize: 12,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.7 : 1,
                }}
                title="새로고침"
              >
                {loading ? '로딩…' : '새로고침'}
              </button>
            )}
            <button
              type="button"
              onClick={copy}
              style={{
                padding: '8px 12px',
                borderRadius: 12,
                border: '1px solid rgba(255, 255, 255, 0.18)',
                background: 'rgba(255, 255, 255, 0.14)',
                color: '#fff',
                fontWeight: 900,
                fontSize: 12,
                cursor: 'pointer',
              }}
              title="클립보드로 복사"
            >
              복사
            </button>
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
        </div>

        <div style={{ padding: 12, flex: 1, minHeight: 0 }}>
          <pre
            ref={preRef}
            className="trader-scroll"
            style={{
              margin: 0,
              height: '100%',
              padding: 14,
              borderRadius: 14,
              border: '1px solid rgba(148, 163, 184, 0.18)',
              background: 'rgba(2, 6, 23, 0.62)',
              color: '#e2e8f0',
              overflow: 'auto',
              fontSize: 12.5,
              lineHeight: 1.5,
              fontFamily: mono,
              whiteSpace: 'pre',
            }}
          >
            {text || '(empty)'}
          </pre>
        </div>
      </div>
    </div>
  )
}

