import { useState } from 'react'
import { theme } from '../../../theme'
import AdminActionButton from './AdminActionButton'
import { useAlert } from '../../../contexts/AlertContext'
import { triggerAdminManualBuy } from '../../../api'

export default function ManualBuyAction() {
  const alert = useAlert()
  const [loading, setLoading] = useState(false)

  const run = async () => {
    const label = '수동 매수'
    const ok = await alert.run({
      title: label,
      message:
        '현재 기준으로 수동 매수를 실행할까요?\n\n- 장외에는 매수 주문이 실패할 수 있습니다.\n- 성공/실패와 무관하게 결과가 텔레그램으로 전송됩니다. (제목에 (수동 매수) 표시)',
      yesText: '실행',
      noText: '취소',
    })
    if (!ok) return

    setLoading(true)
    try {
      const res = await triggerAdminManualBuy()
      if ((res as any)?.success) {
        await alert.ok({
          title: label,
          message: (res as any)?.message ?? '실행 요청 완료. 텔레그램을 확인하세요.',
        })
      } else {
        await alert.warn({
          title: `${label} 실패`,
          message: (res as any)?.message ?? '실행되지 않았습니다. 텔레그램/서버 로그를 확인하세요.',
        })
      }
    } catch (e) {
      await alert.error({ title: `${label} 실패`, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ marginTop: 8, display: 'grid', gap: 10 }}>
      <div style={{ fontSize: 12, color: theme.onSurfaceVariant, lineHeight: 1.45 }}>
        실행 결과는 <b>텔레그램</b>으로 전송됩니다. (기존 포맷 유지 + <b>(수동 매수)</b> 라벨)
      </div>
      <AdminActionButton
        title="수동 매수 실행"
        subtitle="현재 기준으로 매수 로직을 1회 실행하고, 결과를 텔레그램으로 전송"
        onClick={run}
        tone="success"
        disabled={loading}
        right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
      />
    </div>
  )
}

