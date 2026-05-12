import { useCallback, useEffect, useState } from 'react'
import { theme } from '../../../theme'
import SchedulerStatusCard from '../../../components/SchedulerStatusCard'
import AdminActionButton from './AdminActionButton'
import { fmtWhen } from './schedulerShared'
import { useSchedulerPostWithConfirm } from './useSchedulerPostWithConfirm'
import { fetchAdminSchedulersStatus, postAdminSchedulerAction } from '../../../api'

export default function AutoSellSchedulerControl() {
  const { postConfirmed, actionLoading } = useSchedulerPostWithConfirm()
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [intervalMin, setIntervalMin] = useState(1)
  const [note, setNote] = useState('')
  const [nextUtc, setNextUtc] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const r = await fetchAdminSchedulersStatus()
      const s = r.schedules.auto_sell
      setRunning(s.running)
      setIntervalMin(s.interval_min)
      setNote(s.note)
      setNextUtc(s.next_check_at_utc)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const busy = loading || actionLoading

  const run = async (title: string, action: 'start' | 'stop' | 'restart') => {
    const res = await postConfirmed(title, () => postAdminSchedulerAction('auto_sell', action))
    if (res) {
      const s = res.schedules.auto_sell
      setRunning(s.running)
      setIntervalMin(s.interval_min)
      setNote(s.note)
      setNextUtc(s.next_check_at_utc)
    }
  }

  const nextPart = nextUtc != null ? fmtWhen(nextUtc, 'UTC') : '장외/중지'
  const baseline = `${intervalMin}분 간격${note ? ` · ${note}` : ''}`

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <SchedulerStatusCard
        title="스케줄 상태"
        baselineLabel={baseline}
        detailSuffix={`다음 점검(UTC) ${nextPart}`}
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
          subtitle="분 간격 매도 점검 등록"
          tone="success"
          onClick={() => void run('자동 매도 시작', 'start')}
          disabled={busy || running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="중지"
          subtitle="매도 분 잡 해제"
          tone="danger"
          onClick={() => void run('자동 매도 중지', 'stop')}
          disabled={busy || !running}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
        <AdminActionButton
          title="재시작"
          subtitle="한 번 끄고 다시 켬 (실행 중이어도 사용)"
          onClick={() => void run('자동 매도 재시작', 'restart')}
          disabled={busy}
          right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
        />
      </div>
    </div>
  )
}
