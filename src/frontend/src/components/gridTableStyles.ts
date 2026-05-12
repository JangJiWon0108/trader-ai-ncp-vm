import type { CSSProperties } from 'react'
import { theme } from '../theme'

export const monoFont =
  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"

export const thBase: CSSProperties = {
  padding: '12px 12px',
  fontSize: 11,
  fontWeight: 650,
  color: theme.onSurfaceVariant,
  borderBottom: `1px solid ${theme.outline}`,
  whiteSpace: 'nowrap',
}

export const tdBase: CSSProperties = {
  padding: '12px 12px',
  fontSize: 13,
  borderBottom: `1px solid ${theme.surfaceContainer}`,
  color: theme.onSurface,
  fontVariantNumeric: 'tabular-nums',
  verticalAlign: 'top',
  whiteSpace: 'nowrap',
}

export const thDateHead: CSSProperties = {
  ...thBase,
  position: 'sticky',
  left: 0,
  top: 0,
  zIndex: 5,
  background: theme.surface,
  boxShadow: `4px 0 8px -4px ${theme.outline}, 0 1px 0 ${theme.outline}`,
}

export const thColHead: CSSProperties = {
  ...thBase,
  position: 'sticky',
  top: 0,
  zIndex: 3,
  background: theme.surface,
  boxShadow: `0 1px 0 ${theme.outline}`,
}

export const tdStickyLeft: CSSProperties = {
  ...tdBase,
  position: 'sticky',
  left: 0,
  zIndex: 2,
  background: theme.surface,
  boxShadow: `4px 0 8px -4px ${theme.outline}`,
  fontWeight: 800,
}

export const tableScrollBox: CSSProperties = {
  maxHeight: 'min(520px, 64vh)',
  overflow: 'auto',
  border: `1px solid ${theme.outlineSoft}`,
  borderRadius: theme.radiusMd,
}

