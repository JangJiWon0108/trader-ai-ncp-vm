import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import Card from '../../components/Card'
import PageHeader from '../../components/PageHeader'
import CalendarDateField from '../../components/CalendarDateField'
import SortableTh from '../../components/SortableTh'
import DataLoadStatusCard from '../../components/DataLoadStatusCard'
import PaginationBar from '../../components/PaginationBar'
import { theme } from '../../theme'
import { useApi } from '../../hooks/useApi'
import { useTableSort } from '../../hooks/useTableSort'
import { fetchEconomicHistory, fetchEconomicLatest, type EconomicHistoryRow, type EconomicHistoryResponse } from '../../api'

const PAGE_SIZE = 30

const emptyHistory = (): EconomicHistoryResponse => ({
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
})

const ECON: [string, string, string][] = [
  ['10년 기대 인플레이션율','10년 기대 인플레이션율','향후 10년 시장 평균 인플레이션 기대치 (FRED)'],
  ['장단기 금리차','장단기 금리차 (10Y-2Y)','10년 - 2년 국채 수익률 차이 · 음수 → 경기침체 신호'],
  ['기준금리','연준 기준금리','미국 연방준비위원회 기준금리 (FFR)'],
  ['미시간대 소비자 심리지수','미시간 소비자심리','소비자 경기 체감 · 100 기준, 높을수록 낙관'],
  ['실업률','실업률','미국 비농업 실업률 (%) · 낮을수록 고용 호황'],
  ['2년 만기 미국 국채 수익률','미국 2년 국채','단기 금리 기대 반영 수익률'],
  ['10년 만기 미국 국채 수익률','미국 10년 국채','장기 성장·인플레 기대 반영 · 글로벌 기준금리'],
  ['금융스트레스지수','금융 스트레스 지수','FRED FSI · 0↑ 스트레스 상승 / 음수 안정'],
  ['개인 소비 지출','PCE (개인소비지출)','연준 선호 인플레 척도 · 목표 2%'],
  ['소비자 물가지수','CPI','전월/전년 대비 소비자 물가 상승률'],
  ['5년 변동금리 모기지','5년 변동금리 모기지','주택담보대출 금리 · 부동산 선행 지표'],
  ['미국 달러 환율','USD 환율','달러 대 주요 통화 환율 지수'],
  ['통화 공급량 M2','통화공급 M2','현금+예금 합산 유동성 지표'],
  ['가계 부채 비율','가계부채 비율','가처분소득 대비 부채 비율 · 높을수록 리스크'],
  ['GDP 성장률','GDP 성장률','전분기 대비 실질 GDP 성장률 (%)'],
]

const STOCK: [string, string, string][] = [
  ['나스닥 종합지수','나스닥 종합','나스닥 전 종목 시가총액 가중 지수'],
  ['S&P 500 지수','S&P 500','미국 상위 500대 기업 주가 지수 · 시장 벤치마크'],
  ['금 가격','금 가격 (USD/oz)','온스당 국제 금 현물가 · 안전자산 척도'],
  ['달러 인덱스','달러 인덱스 (DXY)','6개 주요 통화 대비 달러 강세 · 100 기준'],
  ['나스닥 100','나스닥 100','시총 상위 100개 비금융주 지수'],
  ['VIX 지수','VIX 공포지수','시장 변동성 기대 · 20↑ 불안 / 30↑ 극공포'],
  ['닛케이 225','닛케이 225','일본 도쿄증권거래소 225개 종목 지수'],
  ['상해종합','상해종합지수','중국 상하이 전체 종목 지수'],
  ['항셍','항셍지수','홍콩 증권거래소 주요 종목 지수'],
  ['달러/엔','USD/JPY','1달러 = 몇 엔'],
  ['달러/위안','USD/CNY','1달러 = 몇 위안'],
  ['애플','AAPL','애플 주식 종가 (USD)'],
  ['마이크로소프트','MSFT','마이크로소프트 주식 종가 (USD)'],
  ['아마존','AMZN','아마존 주식 종가 (USD)'],
  ['구글 A','GOOGL','알파벳 Class A 종가 (USD)'],
  ['메타','META','메타 플랫폼스 종가 (USD)'],
  ['테슬라','TSLA','테슬라 종가 (USD)'],
  ['엔비디아','NVDA','엔비디아 종가 (USD)'],
  ['AMD','AMD','AMD 종가 (USD)'],
  ['브로드컴','AVGO','브로드컴 종가 (USD)'],
]

function fmtVal(v: number | null, key: string) {
  if (v == null) return '—'
  if (/실업률|금리|수익률|인플레이션|모기지|부채|GDP|PCE|스트레스/.test(key)) return `${v.toFixed(2)}%`
  if (/M2|소비 지출/.test(key)) return v.toLocaleString('en-US', { maximumFractionDigits: 0 })
  return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ymdLocal(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function defaultDateRange() {
  const end = new Date()
  const start = new Date(end)
  // "3달" 기본값: 달 기준으로 3개월 전 (대략 90일이 아니라 캘린더 기준)
  start.setMonth(start.getMonth() - 3)
  return { from: ymdLocal(start), to: ymdLocal(end) }
}

const tdSticky: CSSProperties = {
  position: 'sticky',
  left: 0,
  zIndex: 1,
  background: theme.surface,
  fontWeight: 600,
  boxShadow: `4px 0 8px -4px ${theme.outline}`,
}

const thBase: CSSProperties = { padding: '10px 12px', fontSize: 11, fontWeight: 600, color: theme.onSurfaceVariant, borderBottom: `1px solid ${theme.outline}`, whiteSpace: 'nowrap' }
const tdBase: CSSProperties = { padding: '10px 12px', fontSize: 13, borderBottom: `1px solid ${theme.surfaceContainer}`, color: theme.onSurface, fontVariantNumeric: 'tabular-nums' }

const thDateHead: CSSProperties = {
  ...thBase,
  position: 'sticky',
  left: 0,
  top: 0,
  zIndex: 5,
  background: theme.surface,
  boxShadow: `4px 0 8px -4px ${theme.outline}, 0 1px 0 ${theme.outline}`,
}
const thColHead: CSSProperties = {
  ...thBase,
  position: 'sticky',
  top: 0,
  zIndex: 3,
  background: theme.surface,
  boxShadow: `0 1px 0 ${theme.outline}`,
}

const tableScrollBox: CSSProperties = {
  maxHeight: 'min(380px, 48vh)',
  overflow: 'auto',
  border: `1px solid ${theme.outlineSoft}`,
  borderRadius: theme.radiusMd,
}

function EconomicTable({
  rows,
  loading,
  error,
  colDefs,
  awaitingQuery,
}: {
  rows: EconomicHistoryRow[]
  loading: boolean
  error: string | null
  colDefs: [string, string, string][]
  awaitingQuery: boolean
}) {
  const accessors = useMemo(() => {
    const acc: Record<string, (r: EconomicHistoryRow) => string | number | null> = {
      date: (r) => r.date ?? '',
    }
    for (const [key] of colDefs) {
      acc[key] = (r) => {
        const v = r.data[key]
        if (v == null) return null
        if (typeof v === 'number') return Number.isNaN(v) ? null : v
        const n = Number(v)
        return Number.isNaN(n) ? null : n
      }
    }
    return acc
  }, [colDefs])

  const { sortedRows, sortKey, sortDir, requestSort } = useTableSort(rows, accessors, { key: 'date', dir: 'desc' })

  return (
    <div style={{ ...tableScrollBox, opacity: loading ? 0.55 : 1, transition: 'opacity .15s' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: Math.max(640, 160 + colDefs.length * 88) }}>
        <thead>
          <tr>
            <SortableTh
              colId="date"
              label="날짜"
              align="left"
              sortKey={sortKey}
              sortDir={sortDir}
              onSort={requestSort}
              style={{ ...thDateHead, textAlign: 'left' }}
              tip="DB에 저장된 해당 일자의 수집 스냅샷"
            />
            {colDefs.map(([key, label, tip]) => (
              <SortableTh
                key={key}
                colId={key}
                label={label}
                align="right"
                sortKey={sortKey}
                sortDir={sortDir}
                onSort={requestSort}
                style={{ ...thColHead, textAlign: 'right' }}
                tip={tip}
              />
            ))}
          </tr>
        </thead>
        <tbody>
          {awaitingQuery && (
            <tr>
              <td colSpan={colDefs.length + 1} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant, padding: '28px 12px' }}>
                시작일·종료일을 모두 선택한 뒤 <strong style={{ color: theme.onSurface }}>조회</strong>를 누르면 그리드가 채워집니다.
              </td>
            </tr>
          )}
          {!awaitingQuery && !loading && !error && rows.length === 0 && (
            <tr>
              <td colSpan={colDefs.length + 1} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant }}>
                해당 기간에 데이터가 없습니다.
              </td>
            </tr>
          )}
          {!awaitingQuery &&
            sortedRows.map((row) => (
              <tr key={row.date ?? ''} style={{ transition: 'background .12s' }} className="trader-list-row">
                <td style={{ ...tdBase, ...tdSticky }}>{row.date ?? '—'}</td>
                {colDefs.map(([key]) => (
                  <td key={key} style={{ ...tdBase, textAlign: 'right', fontWeight: 600 }}>{fmtVal(row.data[key] ?? null, key)}</td>
                ))}
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Economic() {
  const defaults = useMemo(() => defaultDateRange(), [])
  const [tab, setTab] = useState<'econ' | 'stock'>('econ')
  const [draftFrom, setDraftFrom] = useState(defaults.from)
  const [draftTo, setDraftTo] = useState(defaults.to)
  const [appliedFrom, setAppliedFrom] = useState<string | null>(null)
  const [appliedTo, setAppliedTo] = useState<string | null>(null)
  const [filterHint, setFilterHint] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const queryActive = Boolean(appliedFrom && appliedTo)

  useEffect(() => {
    // 초기 진입 시: 기본값(3달)로 바로 조회 실행
    setAppliedFrom(defaults.from)
    setAppliedTo(defaults.to)
    setFilterHint(null)
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const latest = useApi(fetchEconomicLatest)

  const { data, loading, error } = useApi(
    () => {
      if (!appliedFrom || !appliedTo) return Promise.resolve(emptyHistory())
      return fetchEconomicHistory({ dateFrom: appliedFrom, dateTo: appliedTo, page, pageSize: PAGE_SIZE })
    },
    [appliedFrom, appliedTo, page],
  )

  const rows = data?.items ?? []
  const total = data?.total ?? 0
  const awaitingQuery = !queryActive
  const firstPageLoading = queryActive && loading && rows.length === 0
  const totalPages = total <= 0 ? 0 : Math.ceil(total / PAGE_SIZE)
  const colDefs = tab === 'econ' ? ECON : STOCK

  const runQuery = () => {
    const a = draftFrom.trim()
    const b = draftTo.trim()
    if (!a || !b) {
      setFilterHint('시작일과 종료일을 모두 선택해 주세요.')
      return
    }
    if (a > b) {
      setFilterHint('시작일은 종료일보다 늦을 수 없습니다.')
      return
    }
    setFilterHint(null)
    setAppliedFrom(a)
    setAppliedTo(b)
    setPage(1)
  }

  const tabBtn = (t: typeof tab, label: string) => (
    <button className="trader-btn" onClick={() => setTab(t)} style={{ padding: '8px 18px', borderRadius: theme.radiusMd, fontSize: 13, fontWeight: 700, cursor: 'pointer', border: 'none', background: tab === t ? theme.primary : 'transparent', color: tab === t ? '#fff' : theme.onSurfaceVariant }}>
      {label}
    </button>
  )

  const todayKst = useMemo(() => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
    return `${get('year')}-${get('month')}-${get('day')}`
  }, [])

  const expectedDataDateKst = useMemo(() => {
    // 스케줄이 "오늘" 돌면 "전일" 데이터가 적재되는 전제
    const [y, m, d] = todayKst.split('-').map((v) => Number(v))
    const baseUtc = Date.UTC(y, (m || 1) - 1, d || 1, 0, 0, 0, 0)
    const prev = new Date(baseUtc - 86_400_000)
    const yy = prev.getUTCFullYear()
    const mm = String(prev.getUTCMonth() + 1).padStart(2, '0')
    const dd = String(prev.getUTCDate()).padStart(2, '0')
    return `${yy}-${mm}-${dd}`
  }, [todayKst])

  const latestDate = latest.data?.date ?? null
  const hasExpectedData = Boolean(latestDate && latestDate >= expectedDataDateKst)

  return (
    <div style={{ padding: theme.pagePadding, fontFamily: theme.fontSans, minHeight: '100%' }}>
      <PageHeader title="경제 지표" />
      {error && <div style={{ marginBottom: 16, color: theme.negative, fontSize: 14 }}>오류: {error}</div>}
      {filterHint && <div style={{ marginBottom: 12, color: theme.negative, fontSize: 13 }}>{filterHint}</div>}

      <div style={{ marginBottom: 14 }}>
        <div title={`스케줄이 오늘(KST) 실행되면 전일(${expectedDataDateKst}) 데이터가 적재되는 기준으로 판단합니다.`}>
          <DataLoadStatusCard
            expectedLabel={expectedDataDateKst}
            latestLabel={latestDate}
            loading={latest.loading}
            ok={hasExpectedData}
          />
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end', marginBottom: theme.gutter }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {tabBtn('econ', '경제 지표')}
          {tabBtn('stock', '주요 자산 가격')}
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end', marginLeft: 'auto' }}>
          <CalendarDateField label="시작일" value={draftFrom} onChange={setDraftFrom} />
          <CalendarDateField label="종료일" value={draftTo} onChange={setDraftTo} />
          <button
            type="button"
            className="trader-btn"
            onClick={runQuery}
            style={{
              padding: '10px 22px',
              borderRadius: theme.radiusMd,
              fontSize: 14,
              fontWeight: 700,
              cursor: 'pointer',
              border: 'none',
              background: theme.primary,
              color: '#fff',
              alignSelf: 'flex-end',
            }}
          >
            조회
          </button>
        </div>
      </div>

      <Card title={tab === 'econ' ? `경제 지표 (${colDefs.length}열)` : `주요 자산 (${colDefs.length}열)`}>
        {firstPageLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: theme.onSurfaceVariant }}>로딩 중…</div>
        ) : (
          <>
            {queryActive && loading && rows.length > 0 && (
              <div style={{ fontSize: 12, color: theme.onSurfaceVariant, marginBottom: 8 }}>불러오는 중…</div>
            )}
            <EconomicTable key={tab} rows={rows} loading={loading} error={error} colDefs={colDefs} awaitingQuery={awaitingQuery} />

            {queryActive && totalPages > 0 && (
              <PaginationBar
                page={page}
                totalPages={totalPages}
                pageSize={PAGE_SIZE}
                unitLabel="일"
                loading={loading}
                onPrev={() => setPage((p) => Math.max(1, p - 1))}
                onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
              />
            )}
          </>
        )}
      </Card>
    </div>
  )
}
