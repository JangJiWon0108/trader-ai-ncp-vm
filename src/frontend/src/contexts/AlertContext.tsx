import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import AlertModal, { type AlertKind } from '../components/AlertModal'

type AlertRequest = {
  title?: string
  message: string
  kind: AlertKind
  yesText?: string
  noText?: string
}

type AlertApi = {
  run: (req: Omit<AlertRequest, 'kind'>) => Promise<boolean>
  ok: (req: Omit<AlertRequest, 'kind'>) => Promise<true>
  error: (req: Omit<AlertRequest, 'kind'>) => Promise<true>
  warn: (req: Omit<AlertRequest, 'kind'>) => Promise<true>
}

const AlertContext = createContext<AlertApi | null>(null)

export function AlertProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  const [req, setReq] = useState<AlertRequest | null>(null)
  const resolverRef = useRef<((v: boolean) => void) | null>(null)

  const close = useCallback((v: boolean) => {
    setOpen(false)
    resolverRef.current?.(v)
    resolverRef.current = null
    // 살짝 텀을 두고 요청 제거(애니메이션 고려)
    window.setTimeout(() => setReq(null), 120)
  }, [])

  const show = useCallback((r: AlertRequest) => {
    setReq(r)
    setOpen(true)
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve
    })
  }, [])

  const api = useMemo<AlertApi>(
    () => ({
      run: (r) => show({ ...r, kind: 'run' }),
      ok: async (r) => {
        await show({ ...r, kind: 'ok' })
        return true
      },
      error: async (r) => {
        await show({ ...r, kind: 'error' })
        return true
      },
      warn: async (r) => {
        await show({ ...r, kind: 'warn' })
        return true
      },
    }),
    [show],
  )

  return (
    <AlertContext.Provider value={api}>
      {children}
      <AlertModal
        open={open}
        title={req?.title}
        message={req?.message ?? ''}
        kind={req?.kind ?? 'ok'}
        yesText={req?.yesText}
        noText={req?.noText}
        onYes={() => close(true)}
        onNo={() => close(false)}
        onClose={() => close(false)}
      />
    </AlertContext.Provider>
  )
}

export function useAlert() {
  const ctx = useContext(AlertContext)
  if (!ctx) throw new Error('useAlert must be used within AlertProvider')
  return ctx
}

