import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import Card from '../../components/Card'
import PageHeader from '../../components/PageHeader'
import DataLoadStatusCard from '../../components/DataLoadStatusCard'
import CalendarDateField from '../../components/CalendarDateField'
import SortableTh from '../../components/SortableTh'
import PaginationBar from '../../components/PaginationBar'
import { theme } from '../../theme'
import { useApi } from '../../hooks/useApi'
import { useTableSort } from '../../hooks/useTableSort'
import { fetchAdminSentimentHistory, fetchSentimentStatus, type AdminSentimentHistoryResponse, type AdminSentimentHistoryRow } from '../../api'

export default function AlphaAdvantage() {
  const status = useApi(fetchSentimentStatus)
  const PAGE_SIZE = 30

  const defaults = useMemo(() => {
    const end = new Date()
    const start = new Date(end)
    start.setDate(start.getDate() - 30)
    const fmt = (d: Date) => {
      const y = d.getFullYear()
      const m = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      return `${y}-${m}-${dd}`
    }
    return { from: fmt(start), to: fmt(end) }
  }, [])

  const [draftFrom, setDraftFrom] = useState(defaults.from)
  const [draftTo, setDraftTo] = useState(defaults.to)
  const [appliedFrom, setAppliedFrom] = useState<string | null>(null)
  const [appliedTo, setAppliedTo] = useState<string | null>(null)
  const [filterHint, setFilterHint] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const queryActive = Boolean(appliedFrom && appliedTo)

  useEffect(() => {
    // 경제 지표 페이지와 동일하게: 초기 진입 시 기본 기간으로 자동 조회
    setAppliedFrom(defaults.from)
    setAppliedTo(defaults.to)
    setFilterHint(null)
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const emptyHistory = (): AdminSentimentHistoryResponse => ({
    items: [],
    total: 0,
    page: 1,
    page_size: PAGE_SIZE,
  })

  const { data, loading, error } = useApi(
    () => {
      if (!appliedFrom || !appliedTo) return Promise.resolve(emptyHistory())
      return fetchAdminSentimentHistory({ dateFrom: appliedFrom, dateTo: appliedTo, page, pageSize: PAGE_SIZE })
    },
    [appliedFrom, appliedTo, page],
  )

  const fallbackExpected = useMemo(() => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
    const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
    return `${get('year')}-${get('month')}-${get('day')}`
  }, [])

  const expected = status.data?.today_kst ?? fallbackExpected

  const latestKst = status.data?.latest_kst_date ?? null
  const ok = Boolean(status.data?.today_loaded)

  const thBase: CSSProperties = { padding: '10px 12px', fontSize: 11, fontWeight: 600, color: theme.onSurfaceVariant, borderBottom: `1px solid ${theme.outline}`, whiteSpace: 'nowrap' }

  const tdBase: CSSProperties = {
    padding: '10px 12px',
    fontSize: 13,
    borderBottom: `1px solid ${theme.surfaceContainer}`,
    color: theme.onSurface,
    fontVariantNumeric: 'tabular-nums',
    whiteSpace: 'nowrap',
  }

  const tdSticky: CSSProperties = {
    position: 'sticky',
    left: 0,
    zIndex: 2,
    background: theme.surface,
    boxShadow: `4px 0 8px -4px ${theme.outline}`,
    fontWeight: 800,
  }

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

  const mono =
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"

  const rows: AdminSentimentHistoryRow[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = total <= 0 ? 0 : Math.ceil(total / PAGE_SIZE)
  const awaitingQuery = !queryActive
  const firstPageLoading = queryActive && loading && rows.length === 0
  const accessors = useMemo(() => ({
    date: (r: AdminSentimentHistoryRow) => r.date ?? '',
    ticker: (r: AdminSentimentHistoryRow) => r.ticker ?? '',
    score: (r: AdminSentimentHistoryRow) => r.average_sentiment_score,
    articles: (r: AdminSentimentHistoryRow) => r.article_count,
    calc: (r: AdminSentimentHistoryRow) => r.calculation_date ?? '',
  }), [])

  const { sortedRows, sortKey, sortDir, requestSort } = useTableSort(rows, accessors, { key: 'date', dir: 'desc' })

  const fmtScore = (v: number | null) => {
    if (v == null || Number.isNaN(v)) return '—'
    const s = v >= 0 ? '+' : ''
    return `${s}${v.toFixed(3)}`
  }

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

  return (
    <div style={{ padding: theme.pagePadding, fontFamily: theme.fontSans, minHeight: '100%' }}>
      <PageHeader title="알파 어드밴티지" />

      <div style={{ marginBottom: 14 }}>
        <DataLoadStatusCard
          title="감성 적재 상태"
          expectedLabel={expected}
          latestLabel={latestKst}
          loading={status.loading}
          ok={ok}
        />
      </div>

      {status.error && <div style={{ marginBottom: 16, color: theme.negative, fontSize: 14 }}>오류: {status.error}</div>}
      {error && <div style={{ marginBottom: 16, color: theme.negative, fontSize: 14 }}>오류: {error}</div>}
      {filterHint && <div style={{ marginBottom: 12, color: theme.negative, fontSize: 13 }}>{filterHint}</div>}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-end', marginBottom: theme.gutter }}>
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

      <Card title="감성 히스토리" subtitle="날짜 범위로 조회 · 날짜 기준 정렬/페이지">
        {firstPageLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: theme.onSurfaceVariant }}>로딩 중…</div>
        ) : (
          <>
            {queryActive && loading && rows.length > 0 && (
              <div style={{ fontSize: 12, color: theme.onSurfaceVariant, marginBottom: 8 }}>불러오는 중…</div>
            )}
            <div style={{ maxHeight: 'min(520px, 64vh)', overflow: 'auto', border: `1px solid ${theme.outlineSoft}`, borderRadius: theme.radiusMd }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 860 }}>
                <thead>
                  <tr>
                    <SortableTh
                      colId="date"
                      label="날짜(KST)"
                      align="left"
                      sortKey={sortKey}
                      sortDir={sortDir}
                      onSort={requestSort}
                      style={{ ...thDateHead, textAlign: 'left' }}
                      tip="계산 시각(calculation_date)의 날짜(문자열 기준)"
                    />
                    <SortableTh colId="ticker" label="티커" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                    <SortableTh colId="calc" label="계산시각" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                    <SortableTh colId="score" label="감성 점수" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                    <SortableTh colId="articles" label="기사 수" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                  </tr>
                </thead>
                <tbody style={{ opacity: loading ? 0.55 : 1, transition: 'opacity .15s' }}>
                  {awaitingQuery && (
                    <tr>
                      <td colSpan={5} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant, padding: '28px 12px' }}>
                        시작일·종료일을 모두 선택한 뒤 <strong style={{ color: theme.onSurface }}>조회</strong>를 누르면 그리드가 채워집니다.
                      </td>
                    </tr>
                  )}
                  {!awaitingQuery && !loading && !error && rows.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant }}>
                        해당 기간에 데이터가 없습니다.
                      </td>
                    </tr>
                  )}
                  {!awaitingQuery &&
                    sortedRows.map((r, i) => {
                      const score = r.average_sentiment_score
                      const pos = typeof score === 'number' && score >= 0
                      const scoreColor = score == null ? theme.onSurfaceVariant : pos ? theme.positive : theme.negative
                      return (
                        <tr key={`${r.ticker}-${r.calculation_date ?? i}`} className="trader-list-row">
                          <td style={{ ...tdBase, ...tdSticky, fontFamily: mono }}>{r.date ?? '—'}</td>
                          <td style={{ ...tdBase, fontFamily: mono, fontWeight: 800 }}>{r.ticker}</td>
                          <td style={{ ...tdBase, fontFamily: mono, color: theme.onSurfaceVariant }}>{r.calculation_date ?? '—'}</td>
                          <td style={{ ...tdBase, textAlign: 'right', fontFamily: mono, fontWeight: 900, color: scoreColor }}>
                            {fmtScore(r.average_sentiment_score)}
                          </td>
                          <td style={{ ...tdBase, textAlign: 'right', fontFamily: mono, fontWeight: 800 }}>
                            {r.article_count ?? '—'}
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </div>

            {queryActive && totalPages > 0 && (
              <PaginationBar
                page={page}
                totalPages={totalPages}
                pageSize={PAGE_SIZE}
                unitLabel="행"
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

