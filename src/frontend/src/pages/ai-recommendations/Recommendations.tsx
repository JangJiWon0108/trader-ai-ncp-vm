import type { CSSProperties } from 'react'
import { useState } from 'react'
import Badge from '../../components/Badge'
import Card from '../../components/Card'
import PageHeader from '../../components/PageHeader'
import SortableTh from '../../components/SortableTh'
import Tooltip from '../../components/Tooltip'
import { useTableSort } from '../../hooks/useTableSort'
import { theme } from '../../theme'
import { useApi } from '../../hooks/useApi'
import { fetchAdminPublicConfig, fetchCombinedRecommendations, fetchPredictions, type CombinedRecommendation, type StockPrediction } from '../../api'
import { tdBase, thColHead, tableScrollBox } from '../../components/gridTableStyles'

function fmt(n: number | null | undefined, digits = 2) {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function normalizeRec(rec: string | null | undefined) {
  return String(rec ?? '').trim()
}

function signalVariant(rec: string | null | undefined): 'buy' | 'sell' | 'hold' | 'neutral' {
  const raw = normalizeRec(rec)
  if (!raw) return 'neutral'
  const r = raw.toUpperCase()

  // 영문 케이스: BUY / STRONG BUY / BUYING 등
  if (r.includes('BUY')) return 'buy'
  if (r.includes('SELL')) return 'sell'
  if (r.includes('HOLD')) return 'hold'

  // 한글 케이스: 매수/매도/보유
  if (raw.includes('매수')) return 'buy'
  if (raw.includes('매도')) return 'sell'
  if (raw.includes('보유')) return 'hold'

  return 'neutral'
}

function signalLabel(rec: string | null | undefined) {
  const v = signalVariant(rec)
  if (v === 'buy') return '매수'
  if (v === 'sell') return '매도'
  if (v === 'hold') return '보유'
  return '—'
}

function SentimentDot({ score, threshold }: { score: number | undefined; threshold: number }) {
  if (score == null) return <span style={{ color: theme.onSurfaceVariant }}>—</span>
  const color = score >= threshold ? theme.positive : score <= -threshold ? theme.negative : theme.onSurfaceVariant
  return <span style={{ fontWeight: 700, color }}>{score >= 0 ? '+' : ''}{score.toFixed(3)}</span>
}

// Combined rec row type for sort
type CombRow = CombinedRecommendation & { _type: 'combined' }
const combAccessors: Record<string, (r: CombRow) => string | number> = {
  ticker: (r) => r.ticker,
  stock_name: (r) => r.stock_name,
  recommendation: (r) => r.recommendation,
  rise_probability: (r) => r.rise_probability,
  last_price: (r) => r.last_price,
  predicted_price: (r) => r.predicted_price,
  sentiment_score: (r) => r.sentiment_score ?? r.average_sentiment_score ?? -999,
  accuracy: (r) => r.accuracy ?? 0,
}

// AI prediction row type for sort
type PredRow = StockPrediction & { _type: 'pred' }
const predAccessors: Record<string, (r: PredRow) => string | number> = {
  stock: (r) => r.stock,
  recommendation: (r) => r.recommendation ?? '',
  accuracy: (r) => r.accuracy ?? 0,
  rise_probability: (r) => r.rise_probability ?? 0,
  last_price: (r) => r.last_price ?? 0,
  predicted_price: (r) => r.predicted_price ?? 0,
}

type Tab = 'combined' | 'ai'

export default function Recommendations() {
  const [tab, setTab] = useState<Tab>('combined')

  const { data: cfg } = useApi(fetchAdminPublicConfig)
  const combined = useApi(fetchCombinedRecommendations)
  const aiPreds = useApi(fetchPredictions)

  const sentimentMin = cfg?.buy?.sentiment_min ?? 0.15
  const accMin = cfg?.buy?.model_accuracy_min ?? 70
  const riseMin = cfg?.buy?.rise_prob_min ?? 3

  const combRows: CombRow[] = (combined.data?.results ?? []).map((r) => ({ ...r, _type: 'combined' as const }))
  const predRows: PredRow[] = (aiPreds.data ?? []).map((r) => ({ ...r, _type: 'pred' as const }))

  const {
    sortedRows: sortedComb,
    sortKey: ck,
    sortDir: cd,
    requestSort: cr,
  } = useTableSort(combRows, combAccessors)

  const {
    sortedRows: sortedPred,
    sortKey: pk,
    sortDir: pd,
    requestSort: pr,
  } = useTableSort(predRows, predAccessors)

  const tabStyle = (active: boolean): CSSProperties => ({
    padding: '8px 18px',
    borderRadius: theme.radiusMd,
    fontSize: 13,
    fontWeight: 700,
    cursor: 'pointer',
    border: 'none',
    background: active ? theme.primary : 'transparent',
    color: active ? '#fff' : theme.onSurfaceVariant,
    transition: 'all 0.15s',
  })

  return (
    <div style={{ padding: theme.pagePadding, fontFamily: theme.fontSans, minHeight: '100%' }}>
      <PageHeader title="AI 추천 종목" subtitle="기술적 지표 + 감성분석 + AI 모델 통합 결과" />

      <div style={{ display: 'flex', gap: 8, marginBottom: theme.gutter }}>
        <button className="trader-btn" style={tabStyle(tab === 'combined')} onClick={() => setTab('combined')}>통합 추천 (기술+감성)</button>
        <button className="trader-btn" style={tabStyle(tab === 'ai')} onClick={() => setTab('ai')}>AI 모델 예측</button>
      </div>

      {tab === 'combined' && (
        <Card title="통합 추천 종목" subtitle={`골든크로스·MACD·RSI + 감성점수 ≥ ${sentimentMin} 필터링`}>
          {combined.loading && <div style={{ padding: 20, color: theme.onSurfaceVariant }}>데이터 로딩 중…</div>}
          {combined.error && <div style={{ padding: 20, color: theme.negative }}>오류: {combined.error}</div>}
          {!combined.loading && combRows.length === 0 && <div style={{ padding: 20, color: theme.onSurfaceVariant }}>조건을 만족하는 종목이 없습니다</div>}
          {combRows.length > 0 && (
            <div style={tableScrollBox}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 900 }}>
                <thead>
                  <tr>
                    {[
                      { id: 'ticker', label: '티커' },
                      { id: 'stock_name', label: '종목명' },
                      { id: 'recommendation', label: '신호', tip: 'AI·기술·감성 통합 매수/매도/보유 판단' },
                      { id: 'rise_probability', label: '상승확률', right: true, tip: 'AI 모델 예측 상승 확률 (%)' },
                      { id: 'last_price', label: '현재가', right: true, tip: '가장 최근 실제 체결가 (USD)' },
                      { id: 'predicted_price', label: '예측가', right: true, tip: '딥러닝 모델이 예측한 미래 가격 (USD)' },
                      { id: 'sentiment_score', label: '감성점수', right: true, tip: `뉴스 감성 점수 (-1~1) · ${sentimentMin}↑ 긍정 / -${sentimentMin}↓ 부정` },
                      { id: 'accuracy', label: '정확도', right: true, tip: '모델 백테스트 예측 정확도 (%)' },
                    ].map(({ id, label, right, tip }) => (
                      <SortableTh key={id} colId={id} label={label} align={right ? 'right' : 'left'}
                        sortKey={ck} sortDir={cd} onSort={cr}
                        style={{ ...thColHead, textAlign: right ? 'right' : 'left' }} tip={tip} />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedComb.map((r) => (
                    <tr key={r.ticker}>
                      <td style={{ ...tdBase, fontWeight: 900 }}>{r.ticker}</td>
                      <td style={tdBase}>{r.stock_name}</td>
                      <td style={tdBase}><Badge variant={signalVariant(r.recommendation)}>{signalLabel(r.recommendation)}</Badge></td>
                      <td style={{ ...tdBase, textAlign: 'right', fontWeight: 900, color: r.rise_probability > 0 ? theme.positive : theme.negative }}>
                        {fmt(r.rise_probability, 1)}%
                      </td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>${fmt(r.last_price)}</td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>${fmt(r.predicted_price)}</td>
                      <td style={{ ...tdBase, textAlign: 'right' }}><SentimentDot score={r.sentiment_score ?? r.average_sentiment_score} threshold={sentimentMin} /></td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>{r.accuracy != null ? `${fmt(r.accuracy, 1)}%` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {tab === 'ai' && (
        <Card title="AI 모델 예측" subtitle={`딥러닝 모델 기반 · 정확도 ${accMin}% 이상 + 상승확률 ${riseMin}% 이상`}>
          {aiPreds.loading && <div style={{ padding: 20, color: theme.onSurfaceVariant }}>데이터 로딩 중…</div>}
          {aiPreds.error && <div style={{ padding: 20, color: theme.negative }}>오류: {aiPreds.error}</div>}
          {!aiPreds.loading && predRows.length === 0 && <div style={{ padding: 20, color: theme.onSurfaceVariant }}>데이터 없음</div>}
          {predRows.length > 0 && (
            <div style={tableScrollBox}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 700 }}>
                <thead>
                  <tr>
                    {[
                      { id: 'stock', label: '종목명' },
                      { id: 'recommendation', label: '신호', tip: '딥러닝 모델의 매수/매도/보유 판단' },
                      { id: 'accuracy', label: '정확도', right: true, tip: '모델 백테스트 예측 정확도 (%)' },
                      { id: 'rise_probability', label: '상승확률', right: true, tip: 'AI 모델 예측 상승 확률 (%)' },
                      { id: 'last_price', label: '현재가', right: true, tip: '가장 최근 실제 체결가 (USD)' },
                      { id: 'predicted_price', label: '예측가', right: true, tip: '딥러닝 모델이 예측한 미래 가격 (USD)' },
                    ].map(({ id, label, right, tip }) => (
                      <SortableTh key={id} colId={id} label={label} align={right ? 'right' : 'left'}
                        sortKey={pk} sortDir={pd} onSort={pr}
                        style={{ ...thColHead, textAlign: right ? 'right' : 'left' }} tip={tip} />
                    ))}
                    <th style={thColHead}><Tooltip tip="AI가 생성한 해당 종목 투자 근거 요약">분석 요약</Tooltip></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPred.map((p) => (
                    <tr key={p.stock}>
                      <td style={{ ...tdBase, fontWeight: 900 }}>{p.stock}</td>
                      <td style={tdBase}><Badge variant={signalVariant(p.recommendation)}>{signalLabel(p.recommendation)}</Badge></td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>{p.accuracy != null ? `${fmt(p.accuracy, 1)}%` : '—'}</td>
                      <td style={{ ...tdBase, textAlign: 'right', fontWeight: 900, color: (p.rise_probability ?? 0) > 0 ? theme.positive : theme.negative }}>
                        {fmt(p.rise_probability, 1)}%
                      </td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>${fmt(p.last_price)}</td>
                      <td style={{ ...tdBase, textAlign: 'right' }}>${fmt(p.predicted_price)}</td>
                      <td style={{ ...tdBase, fontSize: 12, color: theme.onSurfaceVariant, maxWidth: 300, whiteSpace: 'normal' }}>
                        {p.analysis ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
