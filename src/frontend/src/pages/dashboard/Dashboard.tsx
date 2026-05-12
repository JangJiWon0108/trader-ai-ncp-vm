import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useNavigate } from 'react-router-dom'
import Card from '../../components/Card'
import PageHeader from '../../components/PageHeader'
import Tooltip from '../../components/Tooltip'
import CurrencyToggle from '../../components/CurrencyToggle'
import EquityChartModal from '../../components/EquityChartModal'
import { theme } from '../../theme'
import { useApi } from '../../hooks/useApi'
import { useCurrency } from '../../contexts/CurrencyContext'
import { formatMoneyFromUsd } from '../../utils/money'
import {
  fetchAllBalances,
  fetchCombinedRecommendations,
  fetchOrderHistory,
  fetchSchedulerStatus,
  fetchEquitySnapshots,
  fetchEconomicLatest,
  fetchAdminInferenceStatus,
  fetchSentimentStatus,
  type EquitySnapshot,
  type KisHolding,
  type OrderHistoryItem,
  type CombinedRecommendation,
} from '../../api'
import { formatKstDateTime } from '../../utils/time'
import { kstYesterdayYmd } from '../admin/components/statusUtils'

const cell: CSSProperties = {
  padding: '12px 14px',
  fontSize: 14,
  fontVariantNumeric: 'tabular-nums',
  borderBottom: `1px solid ${theme.surfaceContainer}`,
}

function fmtPct(n: number | string | null | undefined) {
  const v = typeof n === 'string' ? parseFloat(n) : n
  if (v == null || isNaN(v as number)) return '—'
  const num = v as number
  return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`
}

function fmtNum(n: number | string | null | undefined, digits = 2) {
  const v = typeof n === 'string' ? parseFloat(n) : n
  if (v == null || isNaN(v as number)) return '—'
  return (v as number).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function LoadingRow({ cols }: { cols: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} style={{ ...cell, color: theme.onSurfaceVariant }}>…</td>
      ))}
    </tr>
  )
}

function sortOrderHistoryDesc(rows: OrderHistoryItem[]): OrderHistoryItem[] {
  return [...rows].sort((a, b) => (b.kst_at ?? '').localeCompare(a.kst_at ?? ''))
}

function useCountdownMs(targetIso: string | null | undefined) {
  const [ms, setMs] = useState<number | null>(null)
  useEffect(() => {
    if (!targetIso) {
      setMs(null)
      return
    }
    const t = () => {
      const diff = new Date(targetIso).getTime() - Date.now()
      setMs(diff > 0 ? diff : 0)
    }
    t()
    const id = window.setInterval(t, 1000)
    return () => window.clearInterval(id)
  }, [targetIso])
  return ms
}

function formatCountdown(totalMs: number | null) {
  if (totalMs === null) return '—'
  if (totalMs <= 0) return '곧'
  const s = Math.floor(totalMs / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (d > 0) return `${d}일 ${h}시간 ${m}분`
  if (h > 0) return `${h}시간 ${m}분 ${sec}초`
  if (m > 0) return `${m}분 ${sec}초`
  return `${sec}초`
}

function StatusMini({ running, label }: { running: boolean; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: running ? theme.positive : theme.onSurfaceVariant,
          boxShadow: running ? `0 0 8px ${theme.positive}` : 'none',
        }}
      />
      <span style={{ fontSize: 12, fontWeight: 700, color: theme.onSurfaceVariant }}>{label}</span>
      <span
        style={{
          marginLeft: 'auto',
          fontSize: 11,
          fontWeight: 800,
          padding: '4px 10px',
          borderRadius: 999,
          color: running ? theme.positive : theme.negative,
          background: running ? 'rgba(5,150,105,0.12)' : 'rgba(148,163,184,0.2)',
        }}
      >
        {running ? '실행 중' : '정지'}
      </span>
    </div>
  )
}

function LoadMini({
  ok,
  label,
  loading,
}: {
  ok: boolean
  label: string
  loading: boolean
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: ok ? theme.positive : theme.onSurfaceVariant,
          boxShadow: ok ? `0 0 8px ${theme.positive}` : 'none',
        }}
      />
      <span style={{ fontSize: 12, fontWeight: 800, color: theme.onSurfaceVariant }}>{label}</span>
      <span
        style={{
          fontSize: 11,
          fontWeight: 900,
          padding: '4px 10px',
          borderRadius: 999,
          color: ok ? theme.positive : theme.negative,
          background: ok ? 'rgba(5,150,105,0.12)' : 'rgba(148,163,184,0.2)',
          marginLeft: 'auto',
        }}
      >
        {loading ? '확인 중' : ok ? '완료' : '미완료'}
      </span>
    </div>
  )
}

function scoreOf(r: CombinedRecommendation) {
  return r.composite_score ?? r.rise_probability ?? r.accuracy ?? 0
}

/** KIS `frcr_buy_amt_smtl1`이 비는 경우가 있어, 포트폴리오와 같이 평단×수량으로 보완 */
function lineCostUsd(h: KisHolding): number {
  const fromApi = parseFloat(h.frcr_buy_amt_smtl1 || '0')
  if (!isNaN(fromApi) && fromApi > 0) return fromApi
  const qty = parseFloat(h.ovrs_cblc_qty || '0')
  const avg = parseFloat(h.pchs_avg_pric || '0')
  if (isNaN(qty) || isNaN(avg)) return 0
  return qty * avg
}

function lineEvalUsd(h: KisHolding): number {
  const qty = parseFloat(h.ovrs_cblc_qty || '0')
  const price = parseFloat(h.now_pric2 || '0')
  if (isNaN(qty) || isNaN(price)) return 0
  return qty * price
}

/** 증권사 평가손익(USD) 우선, 없으면 평가−매입 — 상단 카드·표와 동일 기준 */
function linePnlUsd(h: KisHolding): number {
  const kis = parseFloat(h.frcr_evlu_pfls_amt || '')
  if (!isNaN(kis)) return kis
  return lineEvalUsd(h) - lineCostUsd(h)
}

type SortCol = 'ticker' | 'name' | 'qty' | 'avg' | 'price' | 'pnl'

export default function Dashboard() {
  const nav = useNavigate()
  const currency = useCurrency()
  const balance = useApi(fetchAllBalances)
  const recommendations = useApi(fetchCombinedRecommendations)
  const scheduler = useApi(fetchSchedulerStatus)
  const orderHistory = useApi(fetchOrderHistory)
  const equity = useApi(() => fetchEquitySnapshots(14))
  const economicLatest = useApi(fetchEconomicLatest)
  const inference = useApi(fetchAdminInferenceStatus)
  const sentiment = useApi(fetchSentimentStatus)

  const [chartOpen, setChartOpen] = useState(false)
  const [chartMetric, setChartMetric] = useState<'assets' | 'return' | 'seed_return'>('assets')

  const [sort, setSort] = useState<{ col: SortCol; dir: 'asc' | 'desc' }>({ col: 'pnl', dir: 'desc' })

  const holdings: KisHolding[] = balance.data?.output1 ?? []
  const cashUsd = balance.data?.cashUsdBestEffort ?? 0
  // KIS 기준 시드 USD (reset_trading_state_in_db 시점 psamount)
  const seedUsd: number | null = balance.data?.initialCashUsd ?? null

  const totalCost = holdings.reduce((s, h) => s + lineCostUsd(h), 0)
  const totalEval = holdings.reduce((s, h) => s + lineEvalUsd(h), 0)
  const totalPnl = holdings.reduce((s, h) => s + linePnlUsd(h), 0)
  const totalPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0
  const totalAssets = totalEval + (cashUsd > 0 ? cashUsd : 0)

  // 시드 기준 수익률: 총 자산(USD) vs KIS 시드(USD), KRW 표시는 환율 환산
  const usdKrw = currency.usdKrw
  const seedReturnPct = seedUsd && seedUsd > 0 ? ((totalAssets - seedUsd) / seedUsd) * 100 : null
  const seedPnlUsd = seedUsd && seedUsd > 0 ? totalAssets - seedUsd : null
  const seedPnlKrw = seedPnlUsd != null && usdKrw && usdKrw > 0 ? seedPnlUsd * usdKrw : null
  const seedKrw = seedUsd != null && usdKrw && usdKrw > 0 ? seedUsd * usdKrw : null

  const tickers = holdings.map((h) => h.ovrs_pdno).filter(Boolean)
  const winStats = useMemo(() => {
    const withQty = holdings.filter((h) => parseFloat(h.ovrs_cblc_qty || '0') > 0)
    if (!withQty.length) return { rate: null as number | null, n: 0, w: 0 }
    const w = withQty.filter((h) => linePnlUsd(h) > 0).length
    return { rate: (w / withQty.length) * 100, n: withQty.length, w }
  }, [holdings])

  const topRecs = useMemo(() => {
    const list = recommendations.data?.results ?? []
    return [...list]
      .sort((a, b) => scoreOf(b) - scoreOf(a))
      .slice(0, 4)
  }, [recommendations.data])

  const fillRows = useMemo(
    () => sortOrderHistoryDesc((orderHistory.data?.items ?? []).filter((it) => it.success === true)).slice(0, 12),
    [orderHistory.data],
  )

  const sortedHoldings = useMemo(() => {
    const getVal = (h: KisHolding): number | string => {
      switch (sort.col) {
        case 'ticker': return h.ovrs_pdno || ''
        case 'name':   return h.ovrs_item_name || ''
        case 'qty':    return parseFloat(h.ovrs_cblc_qty || '0')
        case 'avg':    return parseFloat(h.pchs_avg_pric || '0')
        case 'price':  return parseFloat(h.now_pric2 || '0')
        case 'pnl': {
          const cost = lineCostUsd(h)
          const pnlAmt = linePnlUsd(h)
          return cost > 0 ? (pnlAmt / cost) * 100 : parseFloat(h.evlu_pfls_rt || '0')
        }
      }
    }
    return [...holdings].sort((a, b) => {
      const av = getVal(a), bv = getVal(b)
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number)
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [holdings, sort])

  const buyCd = useCountdownMs(scheduler.data?.buy_running ? scheduler.data?.next_auto_buy_at : null)
  const sellCd = useCountdownMs(
    scheduler.data?.sell_running && scheduler.data?.next_sell_check_at
      ? scheduler.data.next_sell_check_at
      : null,
  )

  const cardGrid: CSSProperties = {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
    gap: theme.gutter,
    marginBottom: theme.gutter,
  }

  const money = (usd: number | string | null | undefined, opts?: { digitsUsd?: number; digitsKrw?: number; sign?: 'auto' | 'always' | 'never' }) =>
    formatMoneyFromUsd(usd, {
      unit: currency.unit,
      usdKrw: currency.usdKrw,
      digitsUsd: opts?.digitsUsd,
      digitsKrw: opts?.digitsKrw,
      sign: opts?.sign,
    })

  const labelUnit = currency.unit === 'USD' ? 'USD' : 'KRW'

  const econExpected = kstYesterdayYmd()
  const econLatest = economicLatest.data?.date ?? null
  const econOk = Boolean(econLatest && econLatest >= econExpected)

  const infOk = Boolean(inference.data?.inferred_today)

  const sentiOk = Boolean(sentiment.data?.today_loaded)

  return (
    <div style={{ padding: theme.pagePadding, fontFamily: theme.fontSans, minHeight: '100%' }}>
      <PageHeader title="대시보드" subtitle="US 시장 · 8개 요약 카드" right={<CurrencyToggle />} />

      <div style={cardGrid}>
        <Card
          title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <Tooltip
                tip={[
                  '내 계좌의 “현재 총 가치” 표시',
                  '',
                  '총자산 = 주식평가 + 예수금 계산식',
                  '- 주식평가: 보유 주식의 현재가 기준 평가금액',
                  '- 예수금: 투자 전 현금(주문 가능 금액) 기준',
                ].join('\n')}
              >
                {`총 자산 (${labelUnit})`}
              </Tooltip>
              <button
                type="button"
                onClick={() => { setChartMetric('assets'); setChartOpen(true) }}
                style={{
                  padding: '6px 10px',
                  borderRadius: 999,
                  border: '1px solid rgba(148, 163, 184, 0.26)',
                  background: 'rgba(148, 163, 184, 0.12)',
                  color: theme.onSurface,
                  fontSize: 12,
                  fontWeight: 900,
                  cursor: 'pointer',
                }}
                title="총 자산 그래프 보기"
              >
                그래프 보기
              </button>
            </div>
          }
        >
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <div>
              <div
                style={{
                  fontSize: 24,
                  fontWeight: 800,
                  fontVariantNumeric: 'tabular-nums',
                  color: theme.onSurface,
                  fontFamily: theme.fontDisplay,
                  letterSpacing: '-0.03em',
                }}
              >
                {balance.loading ? '로딩 중…' : money(totalAssets, { digitsUsd: 2, digitsKrw: 0 })}
              </div>
              <div style={{ marginTop: 10, fontSize: 12, color: theme.onSurfaceVariant, lineHeight: 1.85 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <span>총자산</span>
                  <strong style={{ color: theme.onSurface, fontVariantNumeric: 'tabular-nums' }}>
                    {balance.loading ? '…' : money(totalAssets, { digitsUsd: 2, digitsKrw: 0 })}
                  </strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <span>주식 평가</span>
                  <span style={{ color: theme.onSurface, fontVariantNumeric: 'tabular-nums' }}>
                    {balance.loading ? '…' : money(totalEval, { digitsUsd: 2, digitsKrw: 0 })}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <span>예수금</span>
                  <span style={{ color: theme.onSurface, fontVariantNumeric: 'tabular-nums' }}>
                    {balance.loading ? '…' : cashUsd > 0 ? money(cashUsd, { digitsUsd: 2, digitsKrw: 0 }) : '—'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <Card
          title={
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <Tooltip
                tip={[
                  '현재 보유 종목의 전체 손익률(%) 표시',
                  '',
                  '총수익률(%) = (평가손익 ÷ 매입원가) × 100 계산식',
                  '- 평가손익: 현재 평가 기준 이익/손실 금액',
                  '- 매입원가: 매입에 사용된 원금(매입금액) 기준',
                ].join('\n')}
              >
                보유종목 수익률 (%)
              </Tooltip>
              <button
                type="button"
                onClick={() => { setChartMetric('return'); setChartOpen(true) }}
                style={{
                  padding: '6px 10px',
                  borderRadius: 999,
                  border: '1px solid rgba(148, 163, 184, 0.26)',
                  background: 'rgba(148, 163, 184, 0.12)',
                  color: theme.onSurface,
                  fontSize: 12,
                  fontWeight: 900,
                  cursor: 'pointer',
                }}
                title="총 수익률 그래프 보기"
              >
                그래프 보기
              </button>
            </div>
          }
        >
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <div>
              <div
                style={{
                  fontSize: 28,
                  fontWeight: 800,
                  fontVariantNumeric: 'tabular-nums',
                  color: totalPct >= 0 ? theme.positive : theme.negative,
                  fontFamily: theme.fontDisplay,
                }}
              >
                {balance.loading ? '…' : fmtPct(totalPct)}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: theme.onSurfaceVariant }}>
                평가손익 {money(totalPnl, { digitsUsd: 2, digitsKrw: 0, sign: 'auto' })}
              </div>
              <div style={{ marginTop: 4, fontSize: 11, color: theme.onSurfaceVariant }}>
                보유 종목 기준 (매입가 대비)
              </div>
            </div>
          </div>
        </Card>

        <Card title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <Tooltip
              tip={[
                '시드 대비 수익률(%) 표시',
                '',
                '시드수익률(%) = (총자산 − 시드) ÷ 시드 × 100 계산식',
                '- 시드: 시작 시점 기준금액',
                '- 손익: 총자산 − 시드 기준 손익금액',
                '',
                '시드 미설정 시 “—” 표시',
              ].join('\n')}
            >
              시드 기준 수익률 (%)
            </Tooltip>
            <button
              type="button"
              onClick={() => { setChartMetric('seed_return'); setChartOpen(true) }}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                border: '1px solid rgba(148, 163, 184, 0.26)',
                background: 'rgba(148, 163, 184, 0.12)',
                color: theme.onSurface,
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
              }}
              title="시드 기준 수익률 그래프 보기"
            >
              그래프 보기
            </button>
          </div>
        }>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <div>
              <div
                style={{
                  fontSize: 28,
                  fontWeight: 800,
                  fontVariantNumeric: 'tabular-nums',
                  color: seedReturnPct == null ? theme.onSurfaceVariant : seedReturnPct >= 0 ? theme.positive : theme.negative,
                  fontFamily: theme.fontDisplay,
                }}
              >
                {balance.loading ? '…' : seedReturnPct == null ? '—' : fmtPct(seedReturnPct)}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: theme.onSurfaceVariant }}>
                시드 {balance.loading ? '…' : seedUsd == null ? '미설정'
                  : currency.unit === 'KRW' && seedKrw != null
                    ? `₩${Math.round(seedKrw).toLocaleString('ko-KR')}`
                    : `$${seedUsd.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
              </div>
              <div style={{ marginTop: 4, fontSize: 12, color: theme.onSurfaceVariant }}>
                총자산 {balance.loading ? '…'
                  : currency.unit === 'KRW' && usdKrw
                    ? `₩${Math.round(totalAssets * usdKrw).toLocaleString('ko-KR')}`
                    : `$${totalAssets.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              </div>
              <div style={{ marginTop: 4, fontSize: 12, color: theme.onSurfaceVariant }}>
                손익 {balance.loading ? '…' : seedPnlUsd == null ? '—'
                  : currency.unit === 'KRW' && seedPnlKrw != null
                    ? `${seedPnlKrw >= 0 ? '+' : ''}₩${Math.round(seedPnlKrw).toLocaleString('ko-KR')}`
                    : `${seedPnlUsd >= 0 ? '+' : ''}$${seedPnlUsd.toFixed(2)}`}
              </div>
            </div>
          </div>
        </Card>

        <Card title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <Tooltip tip="보유 종목">보유 종목 수 + 티커</Tooltip>
            <button
              type="button"
              onClick={() => nav('/portfolio')}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                border: '1px solid rgba(148, 163, 184, 0.26)',
                background: 'rgba(148, 163, 184, 0.12)',
                color: theme.onSurface,
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
              }}
              title="포트폴리오/잔고 페이지로 이동"
            >
              자세히
            </button>
          </div>
        }>
          <div style={{ fontSize: 22, fontWeight: 800, fontFamily: theme.fontDisplay, color: theme.onSurface }}>
            {balance.loading ? '…' : `${holdings.length}개`}
          </div>
          <div
            style={{
              marginTop: 10,
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              maxHeight: 88,
              overflow: 'auto',
            }}
          >
            {!balance.loading &&
              tickers.map((t) => (
                <span
                  key={t}
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    padding: '4px 8px',
                    borderRadius: 6,
                    background: theme.surfaceContainer,
                    color: theme.onSurface,
                  }}
                >
                  {t}
                </span>
              ))}
            {!balance.loading && tickers.length === 0 && (
              <span style={{ fontSize: 12, color: theme.onSurfaceVariant }}>보유 없음</span>
            )}
          </div>
        </Card>

        <Card
          title={<Tooltip tip="보유 종목 중 평가손익(금액)이 0보다 큰 종목 비율(체결 매매 승률과는 다름)">승률 (%)</Tooltip>}
        >
          <div
            style={{
              fontSize: 28,
              fontWeight: 800,
              fontVariantNumeric: 'tabular-nums',
              color: theme.onSurface,
              fontFamily: theme.fontDisplay,
            }}
          >
            {balance.loading ? '…' : winStats.rate == null ? '—' : `${winStats.rate.toFixed(1)}%`}
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: theme.onSurfaceVariant }}>
            {winStats.n ? `${winStats.w} / ${winStats.n} 종목 수익 구간` : '보유 종목 없음'}
          </div>
        </Card>

        <Card title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <Tooltip tip="복합 분석 추천 상위 종목">AI 추천 요약</Tooltip>
            <button
              type="button"
              onClick={() => nav('/recommendations')}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                border: '1px solid rgba(148, 163, 184, 0.26)',
                background: 'rgba(148, 163, 184, 0.12)',
                color: theme.onSurface,
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
              }}
              title="AI 추천 종목 페이지로 이동"
            >
              자세히
            </button>
          </div>
        }>
          {recommendations.loading && <div style={{ color: theme.onSurfaceVariant }}>로딩 중…</div>}
          {recommendations.error && <div style={{ color: theme.negative }}>{recommendations.error}</div>}
          {!recommendations.loading && !recommendations.error && (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {topRecs.length === 0 && <li style={{ fontSize: 13, color: theme.onSurfaceVariant }}>추천 데이터 없음</li>}
              {topRecs.map((r) => (
                <li
                  key={r.ticker}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: `1px solid ${theme.surfaceContainer}`,
                    fontSize: 13,
                  }}
                >
                  <span style={{ fontWeight: 800 }}>{r.ticker}</span>
                  <span style={{ color: theme.onSurfaceVariant, fontVariantNumeric: 'tabular-nums' }}>
                    점수 {fmtNum(scoreOf(r), 1)} · {r.recommendation}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
            <Tooltip tip="최근 매수/매도 주문 내역">최근 주문 내역</Tooltip>
            <button
              type="button"
              onClick={() => nav('/orders')}
              style={{
                padding: '6px 10px',
                borderRadius: 999,
                border: '1px solid rgba(148, 163, 184, 0.26)',
                background: 'rgba(148, 163, 184, 0.12)',
                color: theme.onSurface,
                fontSize: 12,
                fontWeight: 900,
                cursor: 'pointer',
              }}
              title="주문 내역 페이지로 이동"
            >
              자세히
            </button>
          </div>
        }>
          {orderHistory.loading && <div style={{ color: theme.onSurfaceVariant }}>로딩 중…</div>}
          {orderHistory.error && <div style={{ color: theme.negative }}>{orderHistory.error}</div>}
          {!orderHistory.loading && !orderHistory.error && (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, maxHeight: 160, overflow: 'auto' }}>
              {fillRows.length === 0 && <li style={{ fontSize: 13, color: theme.onSurfaceVariant }}>주문 내역 없음</li>}
              {fillRows.map((row) => {
                const isBuy = String(row.side).toLowerCase().includes('buy') || String(row.side).includes('매수')
                const sideLabel = isBuy ? '매수' : '매도'
                const c = isBuy ? theme.positive : theme.negative
                return (
                  <li
                    key={row.id}
                    style={{
                      padding: '8px 0',
                      borderBottom: `1px solid ${theme.surfaceContainer}`,
                      fontSize: 12,
                      lineHeight: 1.45,
                    }}
                  >
                    <span style={{ color: theme.onSurfaceVariant, marginRight: 8 }}>
                      {formatKstDateTime(row.kst_at)}
                    </span>
                    <span style={{ fontWeight: 800, color: c }}>{sideLabel}</span>{' '}
                    <span style={{ fontWeight: 700 }}>{row.ticker}</span>
                    <span style={{ color: theme.onSurfaceVariant }}>
                      {' '}
                      {row.quantity ?? '—'}주 @ {money(row.limit_price, { digitsUsd: 2, digitsKrw: 0 })}
                    </span>
                    {row.success === false && (
                      <span style={{ marginLeft: 6, fontSize: 11, color: theme.negative, fontWeight: 700 }}>실패</span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Card>

        <Card
          title={<Tooltip tip="데이터 적재 현황">데이터 적재 현황</Tooltip>}
          subtitle="경제 데이터 · 모델 추론 · 알파밴티지 감성"
        >
          <LoadMini label="경제 데이터 적재" ok={econOk} loading={economicLatest.loading} />
          <LoadMini label="추론 적재" ok={infOk} loading={inference.loading} />
          <LoadMini label="알파밴티지 적재" ok={sentiOk} loading={sentiment.loading} />
          {(economicLatest.error || inference.error || sentiment.error) && (
            <div style={{ marginTop: 6, fontSize: 12, color: theme.negative, lineHeight: 1.4 }}>
              {(economicLatest.error && `경제: ${economicLatest.error}`) ||
                (inference.error && `추론: ${inference.error}`) ||
                (sentiment.error && `알파밴티지: ${sentiment.error}`)}
            </div>
          )}
        </Card>

        <Card
          title={<Tooltip tip="자동매매 스케줄러 상태와 다음 매수(KST)·장중 매도 점검(뉴욕)까지 남은 시간">자동매매 + 다음 매매</Tooltip>}
        >
          {scheduler.loading && <div style={{ color: theme.onSurfaceVariant }}>로딩 중…</div>}
          {scheduler.error && <div style={{ color: theme.negative }}>{scheduler.error}</div>}
          {!scheduler.loading && !scheduler.error && scheduler.data && (
            <>
              <StatusMini running={scheduler.data.buy_running} label="매수 스케줄" />
              <StatusMini running={scheduler.data.sell_running} label="매도 스케줄" />
              <div style={{ fontSize: 12, color: theme.onSurfaceVariant, marginTop: 4, lineHeight: 1.5 }}>
                <div>
                  <strong style={{ color: theme.onSurface }}>다음 매수</strong>{' '}
                  {scheduler.data.buy_running
                    ? `(${scheduler.data.schedule_buy_time_kst ?? ''} KST 매일) ${formatCountdown(buyCd)}`
                    : `예정 ${formatKstDateTime(scheduler.data.next_auto_buy_at)} · 정지 중`}
                </div>
                <div style={{ marginTop: 4 }}>
                  <strong style={{ color: theme.onSurface }}>다음 매도 점검</strong>{' '}
                  {scheduler.data.sell_running
                    ? scheduler.data.next_sell_check_at
                      ? `${scheduler.data.schedule_sell_interval_min ?? 1}분 간격 · ${formatCountdown(sellCd)}`
                      : '장외 대기 중 (장 개장 시 재개)'
                    : '정지 중 (장중에만 동작)'}
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      <Card title="보유 종목 상세" subtitle="해외주식 잔고 · 나스닥/NYSE/AMEX">
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ color: theme.onSurfaceVariant, fontSize: 12 }}>
                {(
                  [
                    ['티커',  '',   'left',  'ticker'],
                    ['종목명', '',   'left',  'name'],
                    ['수량',  '보유 주식 수 (주)',                                           'right', 'qty'],
                    ['평단',  '매입 평균 단가 (USD)',                                         'right', 'avg'],
                    ['현재가', '현재 실시간 체결가 (USD)',                                      'right', 'price'],
                    ['손익',  '매입(평단×수량 등) 대비 평가 손익률 · 상단 총 수익률과 동일 산식', 'right', 'pnl'],
                  ] as [string, string, string, SortCol][]
                ).map(([label, tip, align, col]) => {
                  const active = sort.col === col
                  const indicator = active ? (sort.dir === 'asc' ? ' ↑' : ' ↓') : ' ↕'
                  return (
                    <th
                      key={col}
                      onClick={() => setSort(s => s.col === col ? { col, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'asc' })}
                      style={{
                        ...cell,
                        fontWeight: 700,
                        textAlign: align as 'left' | 'right',
                        cursor: 'pointer',
                        userSelect: 'none',
                        color: active ? theme.onSurface : theme.onSurfaceVariant,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {tip ? <Tooltip tip={tip}>{label}{indicator}</Tooltip> : <>{label}{indicator}</>}
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {balance.loading && <LoadingRow cols={6} />}
              {balance.error && (
                <tr>
                  <td colSpan={6} style={{ ...cell, color: theme.negative }}>잔고 조회 실패: {balance.error}</td>
                </tr>
              )}
              {!balance.loading && holdings.length === 0 && !balance.error && (
                <tr>
                  <td colSpan={6} style={{ ...cell, color: theme.onSurfaceVariant }}>보유 종목 없음</td>
                </tr>
              )}
              {sortedHoldings.map((h) => {
                const cost = lineCostUsd(h)
                const pnlAmt = linePnlUsd(h)
                const pnlPct = cost > 0 ? (pnlAmt / cost) * 100 : parseFloat(h.evlu_pfls_rt || '0')
                return (
                  <tr key={h.ovrs_pdno} style={{ color: theme.onSurface }}>
                    <td style={{ ...cell, fontWeight: 700 }}>{h.ovrs_pdno}</td>
                    <td style={{ ...cell, fontSize: 13, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.ovrs_item_name}</td>
                    <td style={{ ...cell, textAlign: 'right' }}>{parseFloat(h.ovrs_cblc_qty || '0').toFixed(0)}</td>
                    <td style={{ ...cell, textAlign: 'right' }}>{money(h.pchs_avg_pric, { digitsUsd: 2, digitsKrw: 0 })}</td>
                    <td style={{ ...cell, textAlign: 'right' }}>{money(h.now_pric2, { digitsUsd: 2, digitsKrw: 0 })}</td>
                    <td style={{ ...cell, textAlign: 'right', fontWeight: 700, color: pnlAmt >= 0 ? theme.positive : theme.negative }}>
                      {fmtPct(pnlPct)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      <EquityChartModal
        open={chartOpen}
        title={chartMetric === 'assets' ? '총 자산 그래프' : chartMetric === 'seed_return' ? '시드 기준 수익률 그래프' : '총 수익률 그래프'}
        metric={chartMetric}
        items={(equity.data?.items ?? []) as EquitySnapshot[]}
        loading={equity.loading}
        onClose={() => setChartOpen(false)}
      />
    </div>
  )
}
