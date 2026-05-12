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
import { fetchAdminInferenceHistory, fetchAdminInferenceStatus, type AdminInferenceHistoryResponse, type AdminInferenceHistoryRow } from '../../api'
import { formatKstDateTime } from '../../utils/time'

const PAGE_SIZE = 30

const emptyHistory = (): AdminInferenceHistoryResponse => ({
  items: [],
  total: 0,
  page: 1,
  page_size: PAGE_SIZE,
})

function ymdLocal(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function defaultDateRange() {
  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - 30)
  return { from: ymdLocal(start), to: ymdLocal(end) }
}

function fmtNum(n: number | null | undefined, digits = 1) {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export default function InferenceHistory() {
  const defaults = useMemo(() => defaultDateRange(), [])
  const [draftFrom, setDraftFrom] = useState(defaults.from)
  const [draftTo, setDraftTo] = useState(defaults.to)
  const [appliedFrom, setAppliedFrom] = useState<string | null>(null)
  const [appliedTo, setAppliedTo] = useState<string | null>(null)
  const [filterHint, setFilterHint] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const status = useApi(fetchAdminInferenceStatus)
  const queryActive = Boolean(appliedFrom && appliedTo)

  useEffect(() => {
    setAppliedFrom(defaults.from)
    setAppliedTo(defaults.to)
    setFilterHint(null)
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { data, loading, error } = useApi(
    () => {
      if (!appliedFrom || !appliedTo) return Promise.resolve(emptyHistory())
      return fetchAdminInferenceHistory({ dateFrom: appliedFrom, dateTo: appliedTo, page, pageSize: PAGE_SIZE })
    },
    [appliedFrom, appliedTo, page],
  )

  const rows: AdminInferenceHistoryRow[] = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = total <= 0 ? 0 : Math.ceil(total / PAGE_SIZE)
  const awaitingQuery = !queryActive
  const firstPageLoading = queryActive && loading && rows.length === 0

  const accessors = useMemo(
    () => ({
      data_date: (r: AdminInferenceHistoryRow) => r.data_date ?? '',
      run_date_kst: (r: AdminInferenceHistoryRow) => r.run_date_kst ?? '',
      created_at: (r: AdminInferenceHistoryRow) => r.created_at ?? '',
      stock: (r: AdminInferenceHistoryRow) => r.stock ?? '',
      accuracy: (r: AdminInferenceHistoryRow) => r.accuracy ?? -1,
      rise_probability: (r: AdminInferenceHistoryRow) => r.rise_probability ?? -999,
      last_price: (r: AdminInferenceHistoryRow) => r.last_price ?? -1,
      predicted_price: (r: AdminInferenceHistoryRow) => r.predicted_price ?? -1,
      recommendation: (r: AdminInferenceHistoryRow) => r.recommendation ?? '',
    }),
    [],
  )

  const { sortedRows, sortKey, sortDir, requestSort } = useTableSort(rows, accessors, { key: 'created_at', dir: 'desc' })

  const thBase: CSSProperties = { padding: '10px 12px', fontSize: 11, fontWeight: 600, color: theme.onSurfaceVariant, borderBottom: `1px solid ${theme.outline}`, whiteSpace: 'nowrap' }
  const tdBase: CSSProperties = { padding: '10px 12px', fontSize: 13, borderBottom: `1px solid ${theme.surfaceContainer}`, color: theme.onSurface, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
  const tdSticky: CSSProperties = { position: 'sticky', left: 0, zIndex: 2, background: theme.surface, boxShadow: `4px 0 8px -4px ${theme.outline}`, fontWeight: 800 }
  const thDateHead: CSSProperties = { ...thBase, position: 'sticky', left: 0, top: 0, zIndex: 5, background: theme.surface, boxShadow: `4px 0 8px -4px ${theme.outline}, 0 1px 0 ${theme.outline}` }
  const thColHead: CSSProperties = { ...thBase, position: 'sticky', top: 0, zIndex: 3, background: theme.surface, boxShadow: `0 1px 0 ${theme.outline}` }

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
      <PageHeader title="AI 추론 히스토리" />

      <div style={{ marginBottom: 14 }}>
        <DataLoadStatusCard
          title="추론 적재 상태"
          expectedLabel={status.data?.expected_data_date_kst ?? '—'}
          latestLabel={status.data?.latest_data_date ?? status.data?.latest_kst_date ?? null}
          loading={status.loading}
          ok={Boolean(status.data?.inferred_today)}
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

      <Card title="추론 결과 그리드" subtitle="경제 데이터 증분 적재 후 실행된 추론 결과를 확인합니다.">
        {firstPageLoading ? (
          <div style={{ padding: 32, textAlign: 'center', color: theme.onSurfaceVariant }}>로딩 중…</div>
        ) : (
          <>
            {queryActive && loading && rows.length > 0 && (
              <div style={{ fontSize: 12, color: theme.onSurfaceVariant, marginBottom: 8 }}>불러오는 중…</div>
            )}
            <div style={{ maxHeight: 'min(520px, 64vh)', overflow: 'auto', border: `1px solid ${theme.outlineSoft}`, borderRadius: theme.radiusMd }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 980 }}>
                <thead>
                  <tr>
                    <SortableTh colId="data_date" label="데이터 기준일" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thDateHead, textAlign: 'left' }} />
                    <SortableTh colId="run_date_kst" label="적재일(KST)" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                    <SortableTh colId="created_at" label="적재시각(KST)" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                    <SortableTh colId="stock" label="종목" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                    <SortableTh colId="accuracy" label="정확도(%)" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                    <SortableTh colId="rise_probability" label="상승확률(%)" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                    <SortableTh colId="last_price" label="현재가" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                    <SortableTh colId="predicted_price" label="예측가" align="right" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'right' }} />
                    <SortableTh colId="recommendation" label="추천" align="left" sortKey={sortKey} sortDir={sortDir} onSort={requestSort} style={{ ...thColHead, textAlign: 'left' }} />
                  </tr>
                </thead>
                <tbody style={{ opacity: loading ? 0.55 : 1, transition: 'opacity .15s' }}>
                  {awaitingQuery && (
                    <tr>
                      <td colSpan={9} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant, padding: '28px 12px' }}>
                        시작일·종료일을 모두 선택한 뒤 <strong style={{ color: theme.onSurface }}>조회</strong>를 누르면 그리드가 채워집니다.
                      </td>
                    </tr>
                  )}
                  {!awaitingQuery && !loading && !error && rows.length === 0 && (
                    <tr>
                      <td colSpan={9} style={{ ...tdBase, textAlign: 'center', color: theme.onSurfaceVariant }}>
                        해당 기간에 데이터가 없습니다.
                      </td>
                    </tr>
                  )}
                  {!awaitingQuery &&
                    sortedRows.map((r, i) => (
                      <tr key={`${r.created_at ?? i}-${r.stock ?? ''}`} className="trader-list-row">
                        <td style={{ ...tdBase, ...tdSticky }}>{r.data_date ?? '—'}</td>
                        <td style={{ ...tdBase, color: theme.onSurfaceVariant }}>{r.run_date_kst ?? '—'}</td>
                        <td style={{ ...tdBase, color: theme.onSurfaceVariant }}>{formatKstDateTime(r.created_at)}</td>
                        <td style={{ ...tdBase, fontWeight: 900 }}>{r.stock ?? '—'}</td>
                        <td style={{ ...tdBase, textAlign: 'right', fontWeight: 800 }}>{fmtNum(r.accuracy, 1)}</td>
                        <td style={{ ...tdBase, textAlign: 'right', fontWeight: 900, color: (r.rise_probability ?? 0) >= 0 ? theme.positive : theme.negative }}>
                          {r.rise_probability == null ? '—' : `${r.rise_probability >= 0 ? '+' : ''}${fmtNum(r.rise_probability, 2)}`
                          }
                        </td>
                        <td style={{ ...tdBase, textAlign: 'right' }}>{fmtNum(r.last_price, 2)}</td>
                        <td style={{ ...tdBase, textAlign: 'right' }}>{fmtNum(r.predicted_price, 2)}</td>
                        <td style={{ ...tdBase }}>{r.recommendation ?? '—'}</td>
                      </tr>
                    ))}
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

