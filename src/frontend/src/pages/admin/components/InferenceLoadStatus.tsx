import { useEffect, useState } from 'react'
import DataLoadStatusCard from '../../../components/DataLoadStatusCard'
import AdminActionButton from './AdminActionButton'
import { fetchAdminInferenceStatus, triggerAdminInference } from '../../../api'
import { useAlert } from '../../../contexts/AlertContext'

export default function InferenceLoadStatus() {
  const alert = useAlert()
  const [expected, setExpected] = useState<string>('—')

  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [latest, setLatest] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const check = async () => {
    setLoading(true)
    try {
      const d = await fetchAdminInferenceStatus()
      setExpected(d.expected_data_date_kst ?? d.today_kst ?? '—')
      setLatest(d.latest_data_date ?? d.latest_kst_date)
      setOk(Boolean(d.inferred_today))
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
        title="모델 추론/적재"
        expectedLabel={expected}
        latestLabel={latest}
        loading={loading}
        ok={ok}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <AdminActionButton
          title="적재 확인"
          subtitle="inference/status 조회"
          onClick={check}
          disabled={loading || actionLoading}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>GET</span>}
        />
        <AdminActionButton
          title="추론 실행"
          subtitle="경제 갱신 없이 추론만 수행"
          tone="danger"
          onClick={() => run('모델 추론 + 적재', () => triggerAdminInference())}
          disabled={loading || actionLoading}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}

