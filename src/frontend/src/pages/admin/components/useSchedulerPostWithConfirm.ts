import { useCallback, useState } from 'react'
import type { AdminSchedulerActionResponse } from '../../../api'
import { useAlert } from '../../../contexts/AlertContext'

/** 스케줄러 POST 전 확인 알럿 + 로딩 플래그 */
export function useSchedulerPostWithConfirm() {
  const alert = useAlert()
  const [actionLoading, setActionLoading] = useState(false)

  const postConfirmed = useCallback(
    async (title: string, fn: () => Promise<AdminSchedulerActionResponse>) => {
      const go = await alert.run({ title, message: `${title} 실행할까요?`, yesText: '실행', noText: '취소' })
      if (!go) return null
      setActionLoading(true)
      try {
        const res = await fn()
        await alert.ok({ title, message: res.message || '완료' })
        return res
      } catch (e) {
        await alert.error({ title, message: e instanceof Error ? e.message : String(e) })
        return null
      } finally {
        setActionLoading(false)
      }
    },
    [alert],
  )

  return { postConfirmed, actionLoading }
}
