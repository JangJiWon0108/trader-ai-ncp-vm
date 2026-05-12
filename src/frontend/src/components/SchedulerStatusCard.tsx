import { theme } from '../theme'

/**
 * 관리자 `DataLoadStatusCard`와 동일한 시각(동그라미 + 기준 라벨 + 한 줄 상태)으로
 * 스케줄러 실행 여부를 표시한다.
 */
export default function SchedulerStatusCard({
  title,
  baselineLabel,
  detailSuffix,
  loading,
  running,
}: {
  title: string
  baselineLabel: string
  detailSuffix: string
  loading: boolean
  running: boolean
}) {
  const ok = running
  const dotColor = loading ? '#94a3b8' : ok ? theme.positive : theme.negative
  const dotShadow = loading ? 'none' : `0 0 12px ${dotColor}`

  const secondLine = loading
    ? '확인 중…'
    : ok
      ? `실행 중 · ${detailSuffix || '—'}`
      : `중지 · ${detailSuffix || '—'}`

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
        height: 52,
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
          {title}{' '}
          <span style={{ fontWeight: 800, color: theme.onSurfaceVariant }}>(기준 {baselineLabel})</span>
        </div>
        <div
          style={{
            fontSize: 12,
            color: theme.onSurfaceVariant,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {secondLine}
        </div>
      </div>
    </div>
  )
}
