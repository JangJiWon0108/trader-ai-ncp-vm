import type { ReactNode } from 'react'
import { theme } from '../theme'

export default function Card({
  title,
  subtitle,
  children,
  style,
}: {
  title?: ReactNode
  subtitle?: ReactNode
  children: ReactNode
  style?: React.CSSProperties
}) {
  return (
    <section
      className="trader-card"
      style={{
        position: 'relative',
        background: theme.surface,
        backdropFilter: `saturate(1.15) blur(${theme.blurCard})`,
        WebkitBackdropFilter: `saturate(1.15) blur(${theme.blurCard})`,
        borderRadius: theme.radiusLg,
        border: `1px solid ${theme.outlineSoft}`,
        boxShadow: `${theme.shadow}, 0 0 0 1px rgba(255,255,255,0.5) inset`,
        padding: theme.gutter,
        textAlign: 'left',
        ...style,
      }}
    >
      {(title || subtitle) && (
        <header style={{ marginBottom: title || subtitle ? 16 : 0 }}>
          {title && (
            <h2
              style={{
                margin: 0,
                fontSize: 15,
                fontWeight: 700,
                letterSpacing: '-0.02em',
                color: theme.onSurface,
                fontFamily: theme.fontDisplay,
              }}
            >
              {title}
            </h2>
          )}
          {subtitle && (
            <p
              style={{
                margin: '6px 0 0',
                fontSize: 13,
                color: theme.onSurfaceVariant,
                fontFamily: theme.fontSans,
              }}
            >
              {subtitle}
            </p>
          )}
        </header>
      )}
      {children}
    </section>
  )
}
