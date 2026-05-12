import { useEffect, useState } from 'react'

type RateState = {
  rate: number | null
  loading: boolean
  error: string | null
  updatedAt: string | null
}

async function fetchUsdKrw(): Promise<{ rate: number; updatedAt: string | null }> {
  // 무료 공개 환율 API (키 불필요). 장애 시 상위에서 폴백 처리.
  const res = await fetch('https://open.er-api.com/v6/latest/USD')
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const json = (await res.json()) as any
  const rate = Number(json?.rates?.KRW)
  if (!Number.isFinite(rate) || rate <= 0) throw new Error('invalid KRW rate')
  const updatedAt = typeof json?.time_last_update_utc === 'string' ? json.time_last_update_utc : null
  return { rate, updatedAt }
}

export function useUsdKrwRate(opts?: { refreshMs?: number; initialRate?: number }) {
  const refreshMs = opts?.refreshMs ?? 5 * 60_000
  const initialRate = opts?.initialRate ?? 1350

  const [state, setState] = useState<RateState>({
    rate: initialRate,
    loading: true,
    error: null,
    updatedAt: null,
  })

  useEffect(() => {
    let alive = true
    let timer: number | null = null

    const tick = async () => {
      try {
        const out = await fetchUsdKrw()
        if (!alive) return
        setState({ rate: out.rate, loading: false, error: null, updatedAt: out.updatedAt })
      } catch (e) {
        if (!alive) return
        setState((s) => ({
          ...s,
          loading: false,
          error: e instanceof Error ? e.message : String(e),
        }))
      }
    }

    tick()
    timer = window.setInterval(tick, refreshMs)
    return () => {
      alive = false
      if (timer != null) window.clearInterval(timer)
    }
  }, [refreshMs])

  return state
}

