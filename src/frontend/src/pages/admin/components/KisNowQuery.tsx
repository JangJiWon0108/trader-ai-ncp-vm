import { useState } from 'react'
import { useAlert } from '../../../contexts/AlertContext'
import { theme } from '../../../theme'
import { fetchAllBalances } from '../../../api'
import AdminActionButton from './AdminActionButton'
import { pretty } from './statusUtils'

export default function KisNowQuery() {
  const alert = useAlert()
  const [loading, setLoading] = useState(false)

  const runBalanceAll = async () => {
    const title = 'KIS 잔고/보유종목(전체 거래소)'
    setLoading(true)
    try {
      const data = await fetchAllBalances()
      await alert.ok({ title, message: pretty(data) })
    } catch (e) {
      await alert.error({ title, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ color: theme.onSurfaceVariant, fontSize: 12, lineHeight: 1.5 }}>
        잔고/보유종목을 즉시 조회합니다. (결과는 팝업으로 표시)
      </div>
      <AdminActionButton
        title="잔고/보유종목 조회"
        subtitle="GET /balance/overseas (NASD/NYSE/AMEX 합산)"
        onClick={runBalanceAll}
        disabled={loading}
        right={<span style={{ fontSize: 12, fontWeight: 900 }}>{loading ? '…' : 'GET'}</span>}
      />
    </div>
  )
}

