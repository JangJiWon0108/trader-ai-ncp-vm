import type { CSSProperties } from 'react'
import { theme } from '../theme'

export default function PaginationBar({
  page,
  totalPages,
  pageSize,
  unitLabel = '행',
  loading,
  onPrev,
  onNext,
}: {
  page: number
  totalPages: number
  pageSize: number
  unitLabel?: string
  loading?: boolean
  onPrev: () => void
  onNext: () => void
}) {
  if (totalPages <= 0) return null

  const prevDisabled = page <= 1 || Boolean(loading)
  const nextDisabled = page >= totalPages || Boolean(loading)

  const btn = (disabled: boolean): CSSProperties => ({
    padding: '8px 16px',
    borderRadius: 8,
    border: 'none',
    cursor: disabled ? 'not-allowed' : 'pointer',
    fontSize: 13,
    fontWeight: 800,
    opacity: disabled ? 0.45 : 1,
    background: theme.surfaceContainer,
    color: theme.onSurface,
  })

  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 10,
        alignItems: 'center',
        justifyContent: 'center',
        marginTop: 18,
        paddingTop: 8,
      }}
    >
      <button type="button" className="trader-btn" disabled={prevDisabled} onClick={onPrev} style={btn(prevDisabled)}>
        이전
      </button>
      <span style={{ fontSize: 13, color: theme.onSurfaceVariant, fontVariantNumeric: 'tabular-nums' }}>
        {page} / {totalPages} 페이지 · 페이지당 {pageSize}{unitLabel}
      </span>
      <button type="button" className="trader-btn" disabled={nextDisabled} onClick={onNext} style={btn(nextDisabled)}>
        다음
      </button>
    </div>
  )
}

