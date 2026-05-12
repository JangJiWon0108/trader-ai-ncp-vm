const BASE = (import.meta.env.VITE_API_BASE as string | undefined) || '/api'

async function parseErrorMessage(res: Response) {
  try {
    const ct = res.headers.get('content-type') || ''
    if (ct.includes('application/json')) {
      const data = (await res.json()) as any
      const detail = data?.detail
      if (typeof detail === 'string' && detail.trim()) return detail.trim()
      if (Array.isArray(detail) && detail.length) return JSON.stringify(detail)
      if (typeof data?.message === 'string' && data.message.trim()) return data.message.trim()
      return JSON.stringify(data)
    }
    const text = await res.text()
    return text?.trim() || null
  } catch {
    return null
  }
}

function extractRequestId(res: Response, parsedJsonLike?: any): string | null {
  const hdr = (res.headers.get('x-request-id') || '').trim()
  if (hdr) return hdr
  const bodyRid = typeof parsedJsonLike?.request_id === 'string' ? parsedJsonLike.request_id.trim() : ''
  return bodyRid || null
}

function withTimeout(timeoutMs?: number) {
  const controller = new AbortController()
  const t = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null
  return { controller, clear: () => (t ? clearTimeout(t) : undefined) }
}

async function get<T>(path: string, opts?: { timeoutMs?: number }): Promise<T> {
  const to = withTimeout(opts?.timeoutMs)
  try {
    const res = await fetch(`${BASE}${path}`, { signal: to.controller.signal })
    if (!res.ok) {
      // parseErrorMessage 내부에서 res.json()을 소비하므로, request_id 추출은 header 위주로 한다.
      const msg = await parseErrorMessage(res)
      const rid = extractRequestId(res)
      const suffix = rid ? ` (request_id=${rid})` : ''
      throw new Error(msg ? `${res.status} ${res.statusText} · ${msg}${suffix}` : `${res.status} ${res.statusText}${suffix}`)
    }
    const data = (await res.json()) as T
    return data
  } catch (e: any) {
    // AbortError(타임아웃) 등은 사용자에게 조금 더 명확히 보여준다.
    if (e?.name === 'AbortError') throw new Error('요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.')
    throw e
  } finally {
    to.clear()
  }
}

async function post<T>(path: string, body?: unknown, opts?: { timeoutMs?: number }): Promise<T> {
  const to = withTimeout(opts?.timeoutMs)
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: to.controller.signal,
    })
    if (!res.ok) {
      const msg = await parseErrorMessage(res)
      const rid = extractRequestId(res)
      const suffix = rid ? ` (request_id=${rid})` : ''
      throw new Error(msg ? `${res.status} ${res.statusText} · ${msg}${suffix}` : `${res.status} ${res.statusText}${suffix}`)
    }
    const data = (await res.json()) as T
    return data
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new Error('요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.')
    throw e
  } finally {
    to.clear()
  }
}

// ── Balance ────────────────────────────────────────────────────────
export interface KisHolding {
  ovrs_pdno: string
  ovrs_item_name: string
  ovrs_cblc_qty: string
  pchs_avg_pric: string
  now_pric2: string
  frcr_evlu_pfls_amt: string
  evlu_pfls_rt: string
  frcr_buy_amt_smtl1: string
}

export interface KisOverseasBalance {
  rt_cd: string
  msg1?: string
  output1: KisHolding[]
  output2?: {
    frcr_pchs_amt1?: string
    ovrs_tot_pfls?: string
    tot_evlu_pfls_amt?: string
    tot_pftrt?: string
    evlu_amt_smtl?: string
    frcr_evlu_amt?: string
    frcr_ord_psbl_amt1?: string
    ovrs_ord_psbl_amt?: string
    ord_psbl_frcr_amt?: string
  }
  /** fetchAllBalances: 거래소별 output2 중 주문가능外화 추정 최댓값 */
  cashUsdBestEffort?: number
  /** reset_trading_state_in_db 시점의 KIS 시드 USD (holdings_summary.initial_cash_usd) */
  initialCashUsd?: number | null
}

export const fetchOverseasBalance = (exchange = 'NASD') =>
  get<KisOverseasBalance>(`/balance/overseas?ovrs_excg_cd=${exchange}`)

// All exchanges combined
export async function fetchAllBalances(): Promise<KisOverseasBalance> {
  // 백엔드 `/balance/overseas`가 DB 스냅샷(전체 보유+현금)을 반환하도록 통일되어,
  // 거래소별 3회 호출/합산이 불필요하다.
  return await fetchOverseasBalance('NASD')
}

// ── Stocks / AI predictions ────────────────────────────────────────
export interface StockPrediction {
  stock: string
  accuracy?: number | null
  last_price: number | null
  predicted_price: number | null
  rise_probability: number | null
  recommendation: string | null
  analysis: string | null
}

export const fetchPredictions = () =>
  get<StockPrediction[]>('/stocks/predictions')

// ── Recommendations ────────────────────────────────────────────────
export interface CombinedRecommendation {
  ticker: string
  stock_name: string
  accuracy?: number
  rise_probability: number
  // actual field names from API
  last_price: number
  predicted_price: number
  recommendation: string
  analysis?: string
  sentiment_score?: number
  average_sentiment_score?: number  // alias support
  article_count?: number
  sentiment_date?: string
  calculation_date?: string
  // technical fields
  golden_cross?: boolean
  macd_buy_signal?: boolean
  rsi?: number
  sma20?: number
  sma50?: number
  composite_score?: number
}

export interface RecommendationsResponse {
  results: CombinedRecommendation[]
  message?: string
}

export const fetchCombinedRecommendations = () =>
  get<RecommendationsResponse>('/stocks/recommendations/recommended-stocks/with-technical-and-sentiment')

export const fetchRecommendedStocks = () =>
  get<RecommendationsResponse>('/stocks/recommendations/recommended-stocks')

export const fetchSellCandidates = () =>
  get<{ results: unknown[] }>('/stocks/recommendations/sell-candidates')

// ── Scheduler ─────────────────────────────────────────────────────
export interface SchedulerStatus {
  buy_running: boolean
  sell_running: boolean
  message: string
  schedule_buy_time_kst?: string
  schedule_sell_interval_min?: number
  /** 다음 자동 매수 예정 (KST, ISO8601) */
  next_auto_buy_at?: string
  /** 장중 매도 점검 다음 분(UTC ISO). 장외·매도 중지 시 null */
  next_sell_check_at?: string | null
  /** true=모의투자, false=실전투자 */
  is_mock?: boolean
}

export interface OrderFillRow {
  odno?: string
  ord_dt?: string
  ord_tmd?: string
  pdno?: string
  prdt_name?: string
  sll_buy_dvsn_cd?: string
  sll_buy_dvsn_cd_name?: string
  ft_ccld_qty?: string
  ft_ccld_unpr3?: string
  ft_ccld_amt3?: string
  ovrs_excg_cd?: string
  prcs_stat_name?: string
  [key: string]: string | undefined
}

export interface OrderFillsResponse {
  rt_cd: string
  output: OrderFillRow[]
  count: number
}

export const fetchOrderFills = (days = 30) =>
  get<OrderFillsResponse>(`/balance/order-fills?days=${days}`)

// ── Order history (buy/sell) ───────────────────────────────────────
export interface OrderHistoryItem {
  id: number
  kst_at: string
  ny_trading_date: string | null
  side: 'buy' | 'sell' | string
  ticker: string
  stock_name: string | null
  exchange_code: string | null
  quantity: number | null
  limit_price: number | null
  order_type: string | null
  rt_cd: string | null
  api_message: string | null
  success: boolean | null
  source: string | null
  payload: any | null
  snapshot_holdings_return_pct: number | null
  snapshot_seed_return_pct: number | null
}

export interface OrderHistoryResponse {
  rt_cd: string
  items: OrderHistoryItem[]
  count: number
}

export const fetchOrderHistory = () =>
  get<OrderHistoryResponse>('/balance/order-history')

export const fetchSchedulerStatus = () =>
  get<SchedulerStatus>('/stocks/recommendations/scheduler/status')

export const startBuyScheduler = () =>
  post<{ message: string }>('/stocks/recommendations/purchase/scheduler/start')

export const stopBuyScheduler = () =>
  post<{ message: string }>('/stocks/recommendations/purchase/scheduler/stop')

export const startSellScheduler = () =>
  post<{ message: string }>('/stocks/recommendations/sell/scheduler/start')

export const stopSellScheduler = () =>
  post<{ message: string }>('/stocks/recommendations/sell/scheduler/stop')

export const triggerAdminManualBuy = () =>
  post<{ success: boolean; message: string }>('/admin/buy/trigger')

export const triggerBuy = () =>
  post<{ message: string }>('/stocks/recommendations/purchase/trigger')

export const triggerSell = () =>
  post<{ message: string }>('/stocks/recommendations/sell/trigger')

// ── Alpha Vantage (Sentiment) ──────────────────────────────────────
export interface SentimentStatus {
  today_kst: string
  latest_kst_date: string | null
  latest_calculation_date: string | null
  today_loaded: boolean
}

export const fetchSentimentStatus = () =>
  get<SentimentStatus>('/stocks/recommendations/sentiment/status')

export interface TriggerSentimentUpdateResponse {
  message: string
  skipped?: boolean
  date_kst?: string
  results?: unknown[]
}

export const triggerSentimentUpdate = () =>
  post<TriggerSentimentUpdateResponse>(
    '/stocks/recommendations/recommended-stocks/analyze-news-sentiment',
    undefined,
    { timeoutMs: 300_000 },
  )

// ── Economic ──────────────────────────────────────────────────────
export interface EconomicLatest {
  date: string | null
  data: Record<string, number | null>
}

export const fetchEconomicLatest = () =>
  get<EconomicLatest>('/economic/latest')

export interface EconomicUpdateResponse {
  success: boolean
  message: string
  total_records?: number
  updated_records?: number
}

export const triggerEconomicUpdate = () =>
  post<EconomicUpdateResponse>('/economic/update', undefined, { timeoutMs: 300_000 })

// ── Admin (개인 운영) ───────────────────────────────────────────────
export interface AdminHealth {
  ok: boolean
  project: { name: string; version: string; debug: boolean }
  kis: { use_mock: boolean; base_url: string }
  model: { predict_model_dir: string; resolved_path: string; exists: boolean }
  schedules: unknown
}

export const fetchAdminHealth = () =>
  get<AdminHealth>('/admin/health')

export interface AdminPublicConfig {
  project: { name: string; version: string; is_mock: boolean }
  schedule: {
    auto_buy_time_kst: string
    auto_sell_interval_min: number
    economic_update_time_kst: string
    startup_run_auto_buy: boolean
    after_economic_run_inference: boolean
    eod_llm_report_enabled: boolean
    eod_llm_report_time_kst: string
  }
  buy: {
    model_accuracy_min: number
    rise_prob_min: number
    rsi_max: number
    sentiment_min: number
    tech_min_with_sentiment: number
    tech_min_without_sentiment: number
  }
  sell: {
    take_profit_pct: number
    stop_loss_pct: number
    rsi_overbought: number
    sentiment_max: number
    tech_min_with_sentiment: number
    tech_min_tech_only: number
    tech_min_without_sentiment: number
  }
  trading: {
    buy_quantity: number
    buy_amount_usd: number
    max_positions: number
    order_type: string
  }
}

export const fetchAdminPublicConfig = () =>
  get<AdminPublicConfig>('/admin/config/public')

export interface AdminLogs {
  file: string
  lines: number
  total_lines: number
  text: string
  source?: 'file' | 'memory' | 'none'
  /** 서버 루트 로거에 적용된 최소 레벨(예: INFO면 DEBUG 행은 링버퍼에 없음) */
  log_level?: string
}

export const fetchAdminLogs = (opts?: { lines?: number; file?: string; source?: 'auto' | 'file' | 'memory' }) => {
  const q = new URLSearchParams()
  q.set('lines', String(opts?.lines ?? 250))
  if (opts?.file) q.set('file', opts.file)
  if (opts?.source) q.set('source', opts.source)
  return get<AdminLogs>(`/admin/logs?${q.toString()}`)
}

export const sendAdminTelegramTest = (text?: string) =>
  post<{ sent: boolean; text: string; error?: string | null }>('/admin/telegram/test', { text })

export interface AdminModelInfo {
  predict_model_dir: string
  resolved_path: string
  exists: boolean
  model_meta: unknown
}

export const fetchAdminModelInfo = () =>
  get<AdminModelInfo>('/admin/model')

export interface AdminInferenceStatus {
  today_kst: string
  /** 경제 저장 종료일 가정: 오늘(KST)-1 */
  expected_data_date_kst?: string
  /** predicted_stocks.날짜 최신값 (실제 데이터 기준일) */
  latest_data_date?: string | null
  latest_created_at: string | null
  latest_kst_date: string | null
  inferred_today: boolean
}

export const fetchAdminInferenceStatus = () =>
  get<AdminInferenceStatus>('/admin/inference/status')

export const triggerAdminInference = () =>
  post<{ success: boolean; result: unknown }>('/admin/inference/trigger', undefined, { timeoutMs: 300_000 })

export const triggerAdminEconomicUpdate = () =>
  post<{ success: boolean }>('/admin/economic/trigger')

export const pingAdminKis = () =>
  get<{ ok: boolean; rt_cd: string | null; msg1: string | null; use_mock: boolean }>('/admin/kis/ping')

/** `get_all_schedules_overview()` 응답과 동형 */
export interface AdminSchedulesOverview {
  economic_update: {
    running: boolean
    time_kst: string
    after_run_inference: boolean
    next_run_at_kst: string
  }
  model_inference: { enabled: boolean; trigger: string }
  auto_buy: { running: boolean; time_kst: string; next_run_at_kst: string }
  auto_sell: {
    running: boolean
    interval_min: number
    next_check_at_utc: string | null
    note: string
  }
  eod_llm_report: { enabled: boolean; time_kst: string; next_run_at_kst: string }
}

export interface AdminSchedulersStatusResponse {
  ok: boolean
  schedules: AdminSchedulesOverview
  kis_use_mock: boolean
}

export const fetchAdminSchedulersStatus = () =>
  get<AdminSchedulersStatusResponse>('/admin/schedulers/status')

export interface AdminSchedulerActionResponse {
  ok: boolean
  scheduler: string
  action: string
  message: string
  schedules: AdminSchedulesOverview
  kis_use_mock: boolean
}

export const postAdminSchedulerAction = (scheduler: 'economic' | 'auto_buy' | 'auto_sell', action: 'start' | 'stop' | 'restart') =>
  post<AdminSchedulerActionResponse>(`/admin/schedulers/${scheduler}/${action}`, undefined)

export interface AdminInferenceHistoryRow {
  /** 경제/주가 데이터 기준일 (predicted_stocks 최신 날짜) */
  data_date: string | null
  /** 적재 시각(created_at)을 KST 날짜로만 표기 */
  run_date_kst: string | null
  created_at: string | null
  stock: string | null
  accuracy: number | null
  rise_probability: number | null
  recommendation: string | null
  last_price: number | null
  predicted_price: number | null
}

export interface AdminInferenceHistoryResponse {
  items: AdminInferenceHistoryRow[]
  total: number
  page: number
  page_size: number
}

export function fetchAdminInferenceHistory(opts: {
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}) {
  const q = new URLSearchParams()
  if (opts.dateFrom) q.set('date_from', opts.dateFrom)
  if (opts.dateTo) q.set('date_to', opts.dateTo)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 30))
  return get<AdminInferenceHistoryResponse>(`/admin/inference/history?${q.toString()}`)
}

export interface AdminSentimentRow {
  ticker: string
  average_sentiment_score: number | null
  article_count: number | null
  calculation_date: string | null
}

export const fetchAdminSentimentLatest = (limit = 120) =>
  get<{ items: AdminSentimentRow[]; count: number }>(`/admin/sentiment/latest?limit=${limit}`)

export interface AdminSentimentHistoryRow {
  date: string | null
  ticker: string
  average_sentiment_score: number | null
  article_count: number | null
  calculation_date: string | null
}

export interface AdminSentimentHistoryResponse {
  items: AdminSentimentHistoryRow[]
  total: number
  page: number
  page_size: number
}

export function fetchAdminSentimentHistory(opts: {
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}) {
  const q = new URLSearchParams()
  if (opts.dateFrom) q.set('date_from', opts.dateFrom)
  if (opts.dateTo) q.set('date_to', opts.dateTo)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 30))
  return get<AdminSentimentHistoryResponse>(`/admin/sentiment/history?${q.toString()}`)
}

export interface EconomicHistoryRow {
  date: string | null
  data: Record<string, number | null>
}

export interface EconomicHistoryResponse {
  items: EconomicHistoryRow[]
  total: number
  page: number
  page_size: number
}

export function fetchEconomicHistory(opts: {
  dateFrom?: string
  dateTo?: string
  page?: number
  pageSize?: number
}) {
  const q = new URLSearchParams()
  if (opts.dateFrom) q.set('date_from', opts.dateFrom)
  if (opts.dateTo) q.set('date_to', opts.dateTo)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 10))
  const qs = q.toString()
  return get<EconomicHistoryResponse>(`/economic/history?${qs}`)
}

// ── Orders (NCCS) ─────────────────────────────────────────────────
export interface NccsItem {
  odno?: string
  ord_dt?: string
  ovrs_pdno?: string
  ovrs_item_name?: string
  sll_buy_dvsn_cd_name?: string
  ft_ord_qty?: string
  ft_ccld_qty?: string
  ft_ord_unpr3?: string
  ft_ccld_unpr3?: string
  ovrs_excg_cd?: string
  ord_stat_name?: string
  [key: string]: string | number | undefined
}

export interface NccsResponse {
  rt_cd: string
  msg1?: string
  output?: NccsItem[]
}

export const fetchOrders = (exchange = 'NASD') =>
  get<NccsResponse>(`/balance/nccs?ovrs_excg_cd=${exchange}`)

export async function fetchAllOrders(): Promise<NccsItem[]> {
  const exchanges = ['NASD', 'NYSE', 'AMEX']
  const results = await Promise.allSettled(exchanges.map(fetchOrders))
  const all: NccsItem[] = []
  for (const r of results) {
    if (r.status === 'fulfilled' && (r.value.rt_cd === '0' || r.value.rt_cd === '1')) {
      all.push(...(r.value.output ?? []))
    }
  }
  return all
}

// ── Trading initialize (admin) ─────────────────────────────────────
export const initializeMockTrading = () => post<unknown>('/balance/initialize')

// ── Trading initialize (admin, DB only) ────────────────────────────
export const initializeDbOnly = () => post<unknown>('/balance/initialize-db-only')

// ── Metrics (Equity snapshots) ─────────────────────────────────────
export interface EquitySnapshot {
  snapshot_key: string
  ts_utc: string
  ts_ny: string
  ny_trading_date: string
  stock_value_usd: number
  cash_usd: number
  total_assets_usd: number
  total_cost_usd: number
  total_pnl_usd: number
  total_return_pct: number
  seed_return_pct?: number | null
  source?: string | null
}

export interface EquitySnapshotsResponse {
  ok: boolean
  days: number
  count: number
  items: EquitySnapshot[]
}

export const fetchEquitySnapshots = (days = 7) =>
  get<EquitySnapshotsResponse>(`/metrics/equity?days=${days}`)
