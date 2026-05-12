import type { CSSProperties, KeyboardEvent } from 'react'
import type { SortDirection } from '../hooks/useTableSort'
import Tooltip from './Tooltip'

type Align = 'left' | 'right' | 'center'

export default function SortableTh({
  colId,
  label,
  align = 'left',
  sortKey,
  sortDir,
  onSort,
  style,
  tip,
}: {
  colId: string
  label: string
  align?: Align
  sortKey: string | null
  sortDir: SortDirection
  onSort: (colId: string) => void
  style?: CSSProperties
  tip?: string
}) {
  const active = sortKey === colId
  const mark = !active ? '↕' : sortDir === 'asc' ? '↑' : '↓'

  const onKeyDown = (e: KeyboardEvent<HTMLTableCellElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSort(colId)
    }
  }

  const justify =
    align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start'

  return (
    <th
      className="trader-th-sortable"
      role="columnheader"
      scope="col"
      tabIndex={0}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
      onClick={() => onSort(colId)}
      onKeyDown={onKeyDown}
      style={{
        ...style,
        cursor: 'pointer',
        userSelect: 'none',
        textAlign: align,
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          justifyContent: justify,
          width: '100%',
        }}
      >
        {tip ? (
          <Tooltip tip={tip} placement="below">
            {label}
          </Tooltip>
        ) : (
          label
        )}
        <span
          aria-hidden
          style={{
            fontSize: 10,
            fontWeight: 800,
            opacity: active ? 1 : 0.4,
            flexShrink: 0,
          }}
        >
          {mark}
        </span>
      </span>
    </th>
  )
}
