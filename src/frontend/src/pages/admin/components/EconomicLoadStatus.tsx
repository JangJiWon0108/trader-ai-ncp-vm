import { useEffect, useState } from 'react'
import { theme } from '../../../theme'
import DataLoadStatusCard from '../../../components/DataLoadStatusCard'
import AdminActionButton from './AdminActionButton'
import { kstYesterdayYmd } from './statusUtils'
import { fetchEconomicLatest, triggerAdminEconomicUpdate, triggerEconomicUpdate } from '../../../api'
import { useAlert } from '../../../contexts/AlertContext'

export default function EconomicLoadStatus() {
  const alert = useAlert()
  const expected = kstYesterdayYmd()

  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [latest, setLatest] = useState<string | null>(null)
  // 경제 지표 탭과 동일 기준: expected(전일) 이상이면 적재됨으로 간주
  const ok = Boolean(latest && latest >= expected)

  const check = async () => {
    setLoading(true)
    try {
      const d = await fetchEconomicLatest()
      setLatest(d.date)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void check()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const run = async (label: string, fn: () => Promise<unknown>) => {
    const go = await alert.run({ title: label, message: `${label} 실행할까요?`, yesText: '실행', noText: '취소' })
    if (!go) return
    if (actionLoading) return
    setActionLoading(true)
    try {
      await fn()
      await alert.ok({ title: label, message: '완료' })
      await check()
    } catch (e) {
      await alert.error({ title: label, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <DataLoadStatusCard
        title="경제/주가 적재"
        expectedLabel={expected}
        latestLabel={latest}
        loading={loading}
        ok={ok}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <AdminActionButton
          title="적재 확인"
          subtitle="economic/latest 조회"
          onClick={check}
          disabled={loading || actionLoading}
          right={<span style={{ color: theme.onSurfaceVariant, fontSize: 12, fontWeight: 900 }}>GET</span>}
        />
        <AdminActionButton
          title="증분 수집(기본)"
          subtitle="기존 /economic/update (백그라운드)"
          onClick={() => run('경제 데이터 증분 수집(기본)', () => triggerEconomicUpdate())}
          disabled={loading || actionLoading}
          right={<span style={{ color: theme.onSurfaceVariant, fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="증분 수집(즉시)"
          subtitle="관리자 전용 동기 실행"
          onClick={() => run('경제 데이터 증분 수집(즉시)', () => triggerAdminEconomicUpdate())}
          disabled={loading || actionLoading}
          right={<span style={{ color: theme.onSurfaceVariant, fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}

