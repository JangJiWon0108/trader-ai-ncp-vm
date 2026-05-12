import { theme } from '../theme'
import { useCurrency, type CurrencyUnit } from '../contexts/CurrencyContext'

function PillBtn({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="trader-btn"
      style={{
        padding: '7px 12px',
        borderRadius: 999,
        border: `1px solid ${active ? 'rgba(79,70,229,0.45)' : theme.outlineSoft}`,
        background: active ? 'rgba(79,70,229,0.14)' : theme.surface,
        color: active ? theme.primaryBright : theme.onSurfaceVariant,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: '0.06em',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  )
}

export default function CurrencyToggle({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const { unit, setUnit, usdKrwLoading, usdKrwError } = useCurrency()

  const set = (u: CurrencyUnit) => setUnit(u)
  const help =
    unit === 'KRW' && (usdKrwLoading || usdKrwError)
      ? usdKrwLoading
        ? '환율 로딩…'
        : '환율 오류'
      : null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ display: 'flex', gap: 6, padding: size === 'sm' ? 4 : 6, borderRadius: 999, background: 'rgba(148,163,184,0.12)', border: `1px solid ${theme.outlineSoft}` }}>
        <PillBtn active={unit === 'KRW'} label="KRW" onClick={() => set('KRW')} />
        <PillBtn active={unit === 'USD'} label="USD" onClick={() => set('USD')} />
      </div>
      {help && <span style={{ fontSize: 11, fontWeight: 700, color: theme.onSurfaceVariant }}>{help}</span>}
    </div>
  )
}

