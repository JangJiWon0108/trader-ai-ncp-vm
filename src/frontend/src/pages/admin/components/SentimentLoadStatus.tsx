import { useEffect, useState } from 'react'
import DataLoadStatusCard from '../../../components/DataLoadStatusCard'
import AdminActionButton from './AdminActionButton'
import { kstTodayYmd } from './statusUtils'
import { fetchSentimentStatus, triggerSentimentUpdate } from '../../../api'
import { useAlert } from '../../../contexts/AlertContext'

export default function SentimentLoadStatus() {
  const alert = useAlert()
  const expected = kstTodayYmd()

  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [latest, setLatest] = useState<string | null>(null)
  const [todayLoaded, setTodayLoaded] = useState(false)

  const check = async () => {
    setLoading(true)
    try {
      const d = await fetchSentimentStatus()
      setLatest(d.latest_kst_date)
      setTodayLoaded(Boolean(d.today_loaded))
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
        title="알파밴티지 감성"
        expectedLabel={expected}
        latestLabel={latest}
        loading={loading}
        ok={todayLoaded}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <AdminActionButton
          title="적재 확인"
          subtitle="sentiment/status 조회"
          onClick={check}
          disabled={loading || actionLoading}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>GET</span>}
        />
        <AdminActionButton
          title="감성 업데이트"
          subtitle="Alpha Vantage NEWS_SENTIMENT 적재"
          onClick={() => run('알파밴티지 감성 업데이트', () => triggerSentimentUpdate())}
          disabled={loading || actionLoading}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}

