import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { useUsdKrwRate } from '../hooks/useUsdKrwRate'

export type CurrencyUnit = 'USD' | 'KRW'

type CurrencyContextValue = {
  unit: CurrencyUnit
  setUnit: (u: CurrencyUnit) => void
  usdKrw: number | null
  usdKrwLoading: boolean
  usdKrwUpdatedAt: string | null
  usdKrwError: string | null
}

const CurrencyContext = createContext<CurrencyContextValue | null>(null)

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [unit, setUnit] = useState<CurrencyUnit>('KRW')
  const rate = useUsdKrwRate({ refreshMs: 5 * 60_000, initialRate: 1350 })

  const value = useMemo<CurrencyContextValue>(
    () => ({
      unit,
      setUnit,
      usdKrw: rate.rate,
      usdKrwLoading: rate.loading,
      usdKrwUpdatedAt: rate.updatedAt,
      usdKrwError: rate.error,
    }),
    [unit, rate.rate, rate.loading, rate.updatedAt, rate.error],
  )

  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>
}

export function useCurrency() {
  const ctx = useContext(CurrencyContext)
  if (!ctx) throw new Error('useCurrency must be used within CurrencyProvider')
  return ctx
}

