import type { CurrencyUnit } from '../contexts/CurrencyContext'

export function parseNum(n: number | string | null | undefined): number | null {
  if (n == null) return null
  const v = typeof n === 'string' ? parseFloat(n) : n
  return Number.isFinite(v) ? v : null
}

export function formatMoneyFromUsd(
  usd: number | string | null | undefined,
  opts: {
    unit: CurrencyUnit
    usdKrw: number | null
    digitsUsd?: number
    digitsKrw?: number
    sign?: 'auto' | 'always' | 'never'
  },
) {
  const v = parseNum(usd)
  if (v == null) return '—'

  const signMode = opts.sign ?? 'never'
  const prefix = signMode === 'always' ? (v >= 0 ? '+' : '-') : signMode === 'auto' ? (v >= 0 ? '+' : '') : ''
  const abs = signMode === 'always' ? Math.abs(v) : signMode === 'auto' ? Math.abs(v) : v

  if (opts.unit === 'USD') {
    const digits = opts.digitsUsd ?? 2
    return `${prefix}$${abs.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
  }

  const rate = opts.usdKrw
  if (!rate || !Number.isFinite(rate) || rate <= 0) return '—'
  const digits = opts.digitsKrw ?? 0
  const krw = abs * rate
  return `${prefix}₩${krw.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`
}

