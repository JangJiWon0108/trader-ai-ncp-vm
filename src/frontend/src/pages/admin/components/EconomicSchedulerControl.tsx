import { useCallback, useEffect, useState } from 'react'
import { theme } from '../../../theme'
import SchedulerStatusCard from '../../../components/SchedulerStatusCard'
import AdminActionButton from './AdminActionButton'
import { fmtWhen } from './schedulerShared'
import { useSchedulerPostWithConfirm } from './useSchedulerPostWithConfirm'
import { fetchAdminSchedulersStatus, postAdminSchedulerAction } from '../../../api'

export default function EconomicSchedulerControl() {
  const { postConfirmed, actionLoading } = useSchedulerPostWithConfirm()
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [timeKst, setTimeKst] = useState('—')
  const [afterInference, setAfterInference] = useState(false)
  const [nextAt, setNextAt] = useState('—')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetchAdminSchedulersStatus()
      const e = r.schedules.economic_update
      setRunning(e.running)
      setTimeKst(e.time_kst)
      setAfterInference(e.after_run_inference)
      setNextAt(fmtWhen(e.next_run_at_kst, 'Asia/Seoul'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const busy = loading || actionLoading

  const run = async (title: string, action: 'start' | 'stop' | 'restart') => {
    const res = await postConfirmed(title, () => postAdminSchedulerAction('economic', action))
    if (res) {
      setRunning(res.schedules.economic_update.running)
      setTimeKst(res.schedules.economic_update.time_kst)
      setAfterInference(res.schedules.economic_update.after_run_inference)
      setNextAt(fmtWhen(res.schedules.economic_update.next_run_at_kst, 'Asia/Seoul'))
    }
  }

  const baseline = `매일 ${timeKst} KST · 추론 후행 ${afterInference ? 'ON' : 'OFF'}`
  const detail = `다음 ${nextAt}`

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <SchedulerStatusCard
        title="스케줄 상태"
        baselineLabel={baseline}
        detailSuffix={detail}
        loading={loading}
        running={running}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <AdminActionButton
          title="상태 조회"
          subtitle="/admin/schedulers/status"
          onClick={() => void refresh()}
          disabled={busy}
          right={<span style={{ color: theme.onSurfaceVariant, fontSize: 12, fontWeight: 900 }}>GET</span>}
        />
        <AdminActionButton
          title="시작"
          subtitle="스케줄 등록 후 루프 가동"
          tone="success"
          onClick={() => void run('경제/주가 스케줄 시작', 'start')}
          disabled={busy || running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="중지"
          subtitle="경제 일일 잡 해제"
          tone="danger"
          onClick={() => void run('경제/주가 스케줄 중지', 'stop')}
          disabled={busy || !running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="재시작"
          subtitle="한 번 끄고 다시 켬 (실행 중이어도 사용)"
          onClick={() => void run('경제/주가 스케줄 재시작', 'restart')}
          disabled={busy}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}
