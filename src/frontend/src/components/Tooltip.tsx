import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Placement = 'above' | 'below' | 'auto'

const HIDE_MS = 160

type TooltipProps = {
  tip: string
  children: ReactNode
  /** placement="below" 와 동일 */
  below?: boolean
  placement?: Placement
}

export default function Tooltip({ tip, children, below, placement }: TooltipProps) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const hideT = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [bubble, setBubble] = useState<null | { x: number; y: number; place: 'above' | 'below' }>(null)

  const clearHideTimer = useCallback(() => {
    if (hideT.current != null) {
      clearTimeout(hideT.current)
      hideT.current = null
    }
  }, [])

  const resolvePlacement = useCallback(
    (r: DOMRect): 'above' | 'below' => {
      if (below || placement === 'below') return 'below'
      if (placement === 'above') return 'above'
      return r.top < 96 ? 'below' : 'above'
    },
    [below, placement],
  )

  const openNow = useCallback(() => {
    if (!tip.trim()) return
    const el = wrapRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const place = resolvePlacement(r)
    const x = Math.min(Math.max(r.left + r.width / 2, 16), window.innerWidth - 16)
    const y = place === 'above' ? r.top : r.bottom
    setBubble({ x, y, place })
  }, [tip, resolvePlacement])

  const show = useCallback(() => {
    clearHideTimer()
    openNow()
  }, [clearHideTimer, openNow])

  const scheduleHide = useCallback(() => {
    clearHideTimer()
    hideT.current = window.setTimeout(() => setBubble(null), HIDE_MS)
  }, [clearHideTimer])

  const hideImmediate = useCallback(() => {
    clearHideTimer()
    setBubble(null)
  }, [clearHideTimer])

  useEffect(() => {
    if (!bubble) return
    const h = () => hideImmediate()
    window.addEventListener('scroll', h, true)
    window.addEventListener('resize', h)
    return () => {
      window.removeEventListener('scroll', h, true)
      window.removeEventListener('resize', h)
    }
  }, [bubble, hideImmediate])

  useEffect(() => () => clearHideTimer(), [clearHideTimer])

  return (
    <>
      <span ref={wrapRef} className="tt tt-portal-trigger" onMouseEnter={show} onMouseLeave={scheduleHide}>
        {children}
      </span>
      {bubble &&
        createPortal(
          <div
            role="tooltip"
            className={`tt-portal-bubble tt-portal-bubble--${bubble.place}`}
            style={{
              position: 'fixed',
              left: bubble.x,
              top: bubble.place === 'above' ? bubble.y - 8 : bubble.y + 8,
              transform: bubble.place === 'above' ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
              zIndex: 100000,
              pointerEvents: 'auto',
              whiteSpace: 'pre-line',
            }}
            onMouseEnter={clearHideTimer}
            onMouseLeave={scheduleHide}
          >
            {tip}
          </div>,
          document.body,
        )}
    </>
  )
}
