import { useState, useEffect, useCallback } from 'react'

export interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [rev, setRev] = useState(0)

  const refetch = useCallback(() => setRev((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetcher()
      .then((d) => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch((e: Error) => { if (!cancelled) { setError(e.message); setLoading(false) } })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev, ...deps])

  return { data, loading, error, refetch }
}
