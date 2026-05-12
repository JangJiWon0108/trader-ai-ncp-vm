import { theme } from '../theme'

export default function DataLoadStatusCard({
  title = '적재 상태',
  expectedLabel,
  latestLabel,
  loading,
  ok,
}: {
  title?: string
  expectedLabel: string
  latestLabel: string | null
  loading: boolean
  ok: boolean
}) {
  const dotColor = loading ? '#94a3b8' : ok ? theme.positive : theme.negative
  const dotShadow = loading ? 'none' : `0 0 12px ${dotColor}`

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 12px',
        borderRadius: theme.radiusMd,
        background: theme.surface,
        backdropFilter: `saturate(1.12) blur(${theme.blurCard})`,
        WebkitBackdropFilter: `saturate(1.12) blur(${theme.blurCard})`,
        border: `1px solid ${theme.outlineSoft}`,
        boxShadow: `${theme.shadow}, 0 0 0 1px rgba(255,255,255,0.45) inset`,
        height: 52, // dashboard 카드보다 낮게
        width: 'fit-content',
        maxWidth: 520,
        minWidth: 270,
      }}
    >
      <span
        aria-hidden
        style={{
          width: 10,
          height: 10,
          borderRadius: 999,
          background: dotColor,
          boxShadow: dotShadow,
          flexShrink: 0,
        }}
      />

      <div style={{ display: 'grid', gap: 2, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 900, color: theme.onSurface, letterSpacing: '-0.01em' }}>
          {title} <span style={{ fontWeight: 800, color: theme.onSurfaceVariant }}>(기준 {expectedLabel})</span>
        </div>
        <div style={{ fontSize: 12, color: theme.onSurfaceVariant, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {loading ? '확인 중…' : ok ? `적재됨 · 최신: ${latestLabel}` : `미적재 · 최신: ${latestLabel ?? '없음'}`}
        </div>
      </div>
    </div>
  )
}

