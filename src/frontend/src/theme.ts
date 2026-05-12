/** Trend-forward finance UI tokens (builds on DESIGN.md blues) */
export const theme = {
  fontSans: `'Inter', system-ui, -apple-system, sans-serif`,
  fontDisplay: `'Plus Jakarta Sans', 'Inter', system-ui, sans-serif`,

  /** Main canvas — applied in App as layered backgrounds */
  bgBase: '#f4f6fd',
  bgAccentA: 'rgba(99, 102, 241, 0.18)',
  bgAccentB: 'rgba(14, 165, 233, 0.12)',
  bgAccentC: 'rgba(244, 114, 182, 0.08)',

  surface: 'rgba(255, 255, 255, 0.78)',
  surfaceStrong: '#ffffff',
  surfaceContainer: 'rgba(241, 245, 249, 0.85)',
  onSurface: '#0f172a',
  onSurfaceVariant: '#64748b',
  outline: 'rgba(148, 163, 184, 0.45)',
  outlineSoft: 'rgba(255, 255, 255, 0.65)',

  primary: '#312e81',
  primaryBright: '#4f46e5',
  primaryGlow: 'rgba(79, 70, 229, 0.35)',
  onPrimary: '#ffffff',

  accentCyan: '#06b6d4',
  accentPink: '#ec4899',

  positive: '#059669',
  positiveBg: 'rgba(5, 150, 105, 0.12)',
  negative: '#e11d48',
  negativeBg: 'rgba(225, 29, 72, 0.1)',

  sidebarBg: '#030712',
  sidebarBorder: 'rgba(148, 163, 184, 0.12)',
  sidebarMuted: '#94a3b8',
  sidebarActiveBg: 'linear-gradient(90deg, rgba(99, 102, 241, 0.45) 0%, rgba(59, 130, 246, 0.12) 100%)',
  sidebarActiveGlow: '0 0 24px rgba(99, 102, 241, 0.22)',

  shadow: '0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 12px 28px -8px rgba(15, 23, 42, 0.12)',
  shadowLift: '0 20px 50px -12px rgba(15, 23, 42, 0.18)',

  radiusSm: 10,
  radiusMd: 16,
  radiusLg: 22,
  sidebarWidth: 260,
  pagePadding: 32,
  gutter: 24,

  blurCard: '20px',
} as const

export type Theme = typeof theme
