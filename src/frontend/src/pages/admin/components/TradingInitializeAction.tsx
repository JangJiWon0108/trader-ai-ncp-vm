import { useState } from 'react'
import AdminActionButton from './AdminActionButton'
import { theme } from '../../../theme'
import { useAlert } from '../../../contexts/AlertContext'
import { initializeDbOnly, initializeMockTrading } from '../../../api'

export default function TradingInitializeAction() {
  const alert = useAlert()
  const [loading, setLoading] = useState(false)

  const summaryText = (res: any) => {
    const db = res?.db_reset ?? {}
    const del = db?.delete_status ?? {}
    const seedOk = Boolean(db?.seed_ok ?? db?.holdings_summary_seeded)
    const cashUsd = db?.kis_cash_usd ?? null
    const fx = db?.kis_usdkrw_exrt ?? null

    const kis = res?.kis_reset ?? {}
    const kisAttempted = Boolean(res?.kis_attempted ?? kis?.attempted)
    const kisMarketHours = (res?.kis_market_hours ?? kis?.market_hours) as boolean | undefined
    // 주의: reset_mock_investment()는 skipped를 "항목 리스트"로 반환한다.
    // 장외로 인한 "전체 스킵"은 balance.initialize에서 skipped=true(boolean)로만 내려온다.
    const kisSkippedAll = Boolean(res?.kis_skipped === true || kis?.skipped === true || kisMarketHours === false)
    const kisSuccess = (res?.kis_success ?? kis?.success) as boolean | null | undefined
    const kisError = kis?.error
    const skippedItemsCount = Array.isArray(kis?.skipped) ? kis.skipped.length : 0
    const soldCount = typeof kis?.sold_count === 'number' ? kis.sold_count : Array.isArray(kis?.sold) ? kis.sold.length : 0
    const failedCount =
      typeof kis?.failed_count === 'number' ? kis.failed_count : Array.isArray(kis?.failed) ? kis.failed.length : 0
    const remaining = Array.isArray(kis?.remaining_holdings) ? kis.remaining_holdings : []
    const remainingCount =
      typeof kis?.remaining_count === 'number' ? kis.remaining_count : Array.isArray(remaining) ? remaining.length : 0
    const settled = kis?.settled as boolean | undefined

    const lines: string[] = []

    // 1) DB 테이블별 삭제 결과
    lines.push('[DB 삭제]')
    const keys = ['holdings', 'holdings_summary', 'order_fills', 'open_orders', 'order_history', 'balance_snapshots', 'equity_snapshots']
    for (const k of keys) {
      const st = del?.[k]
      const ok = Boolean(st?.ok)
      const deleted = typeof st?.deleted === 'number' ? st.deleted : null
      const err = st?.error
      lines.push(`- ${k}: ${ok ? '성공' : '실패'}${deleted != null ? ` (deleted=${deleted})` : ''}${!ok && err ? ` · ${String(err)}` : ''}`)
    }

    // 2) Seed 결과(시작 자금)
    lines.push('')
    lines.push('[Seed (시작자금)]')
    lines.push(`- holdings_summary seed: ${seedOk ? '성공' : '실패'}`)
    if (cashUsd != null) lines.push(`- KIS 시드 USD: $${Number(cashUsd).toLocaleString('en-US')}`)
    if (fx != null) lines.push(`- KIS 환율(exrt): ${Number(fx).toLocaleString('en-US')} KRW/USD`)

    // 3) KIS reset 결과(장중에만 시도될 수 있음)
    lines.push('')
    lines.push('[KIS reset]')
    if (kisSkippedAll) {
      lines.push('- 실행: 스킵(장외)')
    } else if (!kisAttempted) {
      lines.push('- 실행: 미시도')
    } else {
      lines.push(`- 실행: ${kisSuccess === false ? '실패' : '성공/완료'}`)
      if (kisSuccess === false && kisError) lines.push(`- 오류: ${String(kisError)}`)
      if (skippedItemsCount > 0) lines.push(`- 스킵(일부 종목): ${skippedItemsCount}건`)
      lines.push(`- 매도 성공: ${soldCount}건`)
      lines.push(`- 매도 실패: ${failedCount}건`)
      if (typeof settled === 'boolean') lines.push(`- 잔고 0 정착(settled): ${settled ? '예' : '아니오'}`)
      lines.push(`- 잔여 보유: ${remainingCount}개`)
      if (remainingCount > 0) {
        for (const it of remaining.slice(0, 20)) {
          const t = String(it?.ticker ?? '')
          const q = it?.qty != null ? String(it.qty) : ''
          lines.push(`  - ${t}${q ? ` (${q})` : ''}`)
        }
        if (remainingCount > 20) lines.push(`  - ... 외 ${remainingCount - 20}개`)
      }
    }

    return lines.join('\n')
  }

  const runInitialize = async () => {
    const go = await alert.run({
      title: '모의투자 초기화',
      message:
        '정말 초기화할까요?\n\n- KIS 전량 매도(가능하면) 시도\n- Supabase 거래 상태(holdings/order_fills/open_orders 등)만 초기화\n- 경제/추론/감성 데이터는 유지\n\n이 작업은 되돌릴 수 없어요.',
      yesText: '초기화',
      noText: '취소',
    })
    if (!go) return

    setLoading(true)
    try {
      const res = await initializeMockTrading()
      const r = res as any
      const kis = r?.kis_reset
      const kisAttempted = Boolean(kis?.attempted)
      const kisMarketHours = (r?.kis_market_hours ?? kis?.market_hours) as boolean | undefined
      const kisSkippedAll = Boolean(r?.kis_skipped === true || kis?.skipped === true || kisMarketHours === false)
      const kisSuccess = kis?.success

      // DB 초기화는 수행되고, KIS reset은 장외/제한 등으로 스킵/실패할 수 있음 → 프론트에 명확히 경고
      if (kisSkippedAll) {
        await alert.warn({
          title: '초기화 완료(장외: KIS 스킵)',
          message: summaryText(res),
        })
      } else if (kisAttempted && kisSuccess === false) {
        await alert.warn({
          title: '초기화 완료(KIS 일부 실패)',
          message: summaryText(res),
        })
      } else {
        await alert.ok({ title: '초기화 완료', message: summaryText(res) })
      }
    } catch (e) {
      // 409 등 객체 detail이 넘어오는 경우 메시지에 포함되도록 한다.
      const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : JSON.stringify(e, null, 2)
      await alert.error({ title: '초기화 실패', message: msg })
    } finally {
      setLoading(false)
    }
  }

  const runDbOnly = async () => {
    const go = await alert.run({
      title: 'DB만 초기화',
      message:
        'DB만 초기화할까요?\n\n- KIS(한투) 계좌는 건드리지 않습니다.\n- Supabase 거래 상태 + 매매 로그를 초기화합니다.\n- 시작 자금(5억) 시드를 다시 넣습니다.\n\n※ 한투 사이트에서 모의투자 초기화를 이미 했거나, 지금 할 예정일 때 사용하세요.',
      yesText: 'DB 초기화',
      noText: '취소',
    })
    if (!go) return

    setLoading(true)
    try {
      const res = await initializeDbOnly()
      await alert.ok({ title: 'DB 초기화 완료', message: summaryText(res) })
    } catch (e) {
      const msg = e instanceof Error ? e.message : typeof e === 'string' ? e : JSON.stringify(e, null, 2)
      await alert.error({ title: 'DB 초기화 실패', message: msg })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ color: theme.onSurfaceVariant, fontSize: 12, lineHeight: 1.5 }}>
        거래 상태 스냅샷을 비우고 다시 시작합니다. (경제/추론/감성은 유지)
      </div>
      <AdminActionButton
        title="모의투자 초기화(거래 상태 리셋)"
        subtitle="POST /balance/initialize"
        tone="danger"
        disabled={loading}
        onClick={runInitialize}
        right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
      />
      <AdminActionButton
        title="DB만 초기화(거래 상태+로그)"
        subtitle="POST /balance/initialize-db-only"
        tone="warning"
        disabled={loading}
        onClick={runDbOnly}
        right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
      />
    </div>
  )
}

