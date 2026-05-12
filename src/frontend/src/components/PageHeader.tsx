import { useApi } from '../hooks/useApi'
import { fetchSchedulerStatus } from '../api'
import { theme } from '../theme'

export default function PageHeader({
  title,
  subtitle,
  right,
}: {
  title: string
  subtitle?: string
  right?: React.ReactNode
}) {
  const scheduler = useApi(fetchSchedulerStatus)
  const isMock = scheduler.data?.is_mock ?? true
  const pillLabel = isMock ? '모의 투자' : '실제 투자'
  const pillColor = isMock ? theme.primaryBright : theme.positive
  const pillBg = isMock ? 'rgba(79, 70, 229, 0.1)' : 'rgba(5, 150, 105, 0.1)'
  const pillBorder = isMock ? 'rgba(79, 70, 229, 0.2)' : 'rgba(5, 150, 105, 0.25)'

  return (
    <header style={{ marginBottom: theme.gutter }}>
      <div
        className="trader-preview-pill"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 12px',
          borderRadius: 999,
          fontFamily: theme.fontSans,
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          color: pillColor,
          background: pillBg,
          border: `1px solid ${pillBorder}`,
          marginBottom: 12,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: pillColor,
            boxShadow: `0 0 8px ${pillColor}`,
          }}
        />
        {pillLabel}
      </div>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <h1
          style={{
            margin: 0,
            fontSize: 32,
            fontWeight: 800,
            letterSpacing: '-0.035em',
            lineHeight: 1.15,
            fontFamily: theme.fontDisplay,
            background: `linear-gradient(105deg, ${theme.onSurface} 0%, ${theme.primaryBright} 55%, ${theme.accentCyan} 100%)`,
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          {title}
        </h1>
        {right && <div style={{ marginLeft: 'auto', paddingTop: 2 }}>{right}</div>}
      </div>
      {subtitle && (
        <p
          style={{
            margin: '10px 0 0',
            fontSize: 15,
            lineHeight: 1.55,
            color: theme.onSurfaceVariant,
            fontFamily: theme.fontSans,
            maxWidth: 520,
          }}
        >
          {subtitle}
        </p>
      )}
    </header>
  )
}
