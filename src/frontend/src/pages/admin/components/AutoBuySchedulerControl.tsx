import { useCallback, useEffect, useState } from 'react'
import { theme } from '../../../theme'
import SchedulerStatusCard from '../../../components/SchedulerStatusCard'
import AdminActionButton from './AdminActionButton'
import { fmtWhen } from './schedulerShared'
import { useSchedulerPostWithConfirm } from './useSchedulerPostWithConfirm'
import { fetchAdminSchedulersStatus, postAdminSchedulerAction } from '../../../api'

export default function AutoBuySchedulerControl() {
  const { postConfirmed, actionLoading } = useSchedulerPostWithConfirm()
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [timeKst, setTimeKst] = useState('—')
  const [nextAt, setNextAt] = useState('—')

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetchAdminSchedulersStatus()
      const b = r.schedules.auto_buy
      setRunning(b.running)
      setTimeKst(b.time_kst)
      setNextAt(fmtWhen(b.next_run_at_kst, 'Asia/Seoul'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const busy = loading || actionLoading

  const run = async (title: string, action: 'start' | 'stop' | 'restart') => {
    const res = await postConfirmed(title, () => postAdminSchedulerAction('auto_buy', action))
    if (res) {
      setRunning(res.schedules.auto_buy.running)
      setTimeKst(res.schedules.auto_buy.time_kst)
      setNextAt(fmtWhen(res.schedules.auto_buy.next_run_at_kst, 'Asia/Seoul'))
    }
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <SchedulerStatusCard
        title="스케줄 상태"
        baselineLabel={`매일 ${timeKst} KST`}
        detailSuffix={`다음 ${nextAt}`}
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
          subtitle="매수 일일 잡 등록"
          tone="success"
          onClick={() => void run('자동 매수 시작', 'start')}
          disabled={busy || running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="중지"
          subtitle="매수 일일 잡 해제"
          tone="danger"
          onClick={() => void run('자동 매수 중지', 'stop')}
          disabled={busy || !running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="재시작"
          subtitle="한 번 끄고 다시 켬 (실행 중이어도 사용)"
          onClick={() => void run('자동 매수 재시작', 'restart')}
          disabled={busy}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}
