import { useEffect, useMemo } from 'react'
import { theme } from '../theme'
import type { EquitySnapshot } from '../api'

type Metric = 'assets' | 'return' | 'seed_return'

const KR_DAYS = ['일', '월', '화', '수', '목', '금', '토']
const KST_TZ = 'Asia/Seoul'
const SLOT_MINUTES = (() => {
  const out: { hh: number; mm: number }[] = []
  // 22:30 ~ 23:50
  for (let mm = 30; mm <= 50; mm += 10) out.push({ hh: 22, mm })
  for (let mm = 0; mm <= 50; mm += 10) out.push({ hh: 23, mm })
  // 00:00 ~ 04:50
  for (let hh = 0; hh <= 4; hh++) for (let mm = 0; mm <= 50; mm += 10) out.push({ hh, mm })
  // 05:00
  out.push({ hh: 5, mm: 0 })
  return out
})()

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

function ymd(y: number, m: number, d: number) {
  return `${y}-${pad2(m)}-${pad2(d)}`
}

function fmtSlotLabelKst(hh: number, mm: number) {
  return `${pad2(hh)}:${pad2(mm)}`
}

function kstPartsFromIso(iso: string): { y: number; m: number; d: number; hh: number; mm: number } | null {
  const dt = new Date(iso)
  if (Number.isNaN(dt.getTime())) return null
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: KST_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(dt)
  const get = (type: string) => parts.find((p) => p.type === type)?.value
  const y = Number(get('year'))
  const m = Number(get('month'))
  const d = Number(get('day'))
  const hh = Number(get('hour'))
  const mm = Number(get('minute'))
  if (![y, m, d, hh, mm].every((x) => Number.isFinite(x))) return null
  return { y, m, d, hh, mm }
}

function addDays(ymdKey: string, days: number) {
  const [y, m, d] = ymdKey.split('-').map((x) => parseInt(x, 10))
  const base = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1, 12, 0, 0))
  base.setUTCDate(base.getUTCDate() + days)
  return ymd(base.getUTCFullYear(), base.getUTCMonth() + 1, base.getUTCDate())
}

function dayOfWeek(ymdKey: string) {
  const [y, m, d] = ymdKey.split('-').map((x) => parseInt(x, 10))
  const dt = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1, 12, 0, 0))
  return dt.getUTCDay() // 0=일..6=토
}

function currentWeekRangeKst(): { startKey: string; thuKey: string } | null {
  const nowIso = new Date().toISOString()
  const p = kstPartsFromIso(nowIso)
  if (!p) return null
  const calendarKey = ymd(p.y, p.m, p.d)
  // 00:00~05:59 KST는 전날 22:30 세션에 속하므로 하루 앞으로
  const sessionKey = p.hh < 6 ? addDays(calendarKey, -1) : calendarKey
  const dow = dayOfWeek(sessionKey)
  // 이번 주 월요일(세션 기준)
  const daysFromMon = (dow - 1 + 7) % 7
  const startKey = addDays(sessionKey, -daysFromMon)
  // 이번 주 목요일
  const daysToThu = (4 - dow + 7) % 7
  const thuKey = addDays(sessionKey, daysToThu)
  return { startKey, thuKey }
}

function fmtMoney(n: number) {
  if (!isFinite(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

function fmtPct(n: number) {
  if (!isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtYLabel(v: number, metric: Metric) {
  if (metric === 'assets') return `$${fmtMoney(v)}`
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

// session_date(YYYY-MM-DD, KST) → "월 5/12" 형태
function fmtDayLabel(sessionKstYmd: string) {
  const d = dayOfWeek(sessionKstYmd)
  const day = KR_DAYS[d] ?? ''
  const [_y, m, dd] = sessionKstYmd.split('-').map((x) => parseInt(x, 10))
  return { day, date: `${m}/${dd}` }
}

type SlotPoint = {
  x: number
  sessionYmd: string
  hh: number
  mm: number
  v: number | null
  raw?: EquitySnapshot
}

function valueOf(x: EquitySnapshot, metric: Metric): number | null {
  if (metric === 'assets') return isFinite(x.total_assets_usd) ? x.total_assets_usd : null
  if (metric === 'seed_return') return x.seed_return_pct != null && isFinite(x.seed_return_pct) ? x.seed_return_pct : null
  return isFinite(x.total_return_pct) ? x.total_return_pct : null
}

function toSeries(items: EquitySnapshot[], metric: Metric) {
  const range = currentWeekRangeKst()
  if (!range) return { points: [] as SlotPoint[], sessions: [] as string[] }
  const { startKey, thuKey } = range

  // 이번 주 월요일..목요일 (inclusive)
  const sessions: string[] = []
  let cur = startKey
  for (let i = 0; i < 7; i++) {
    sessions.push(cur)
    if (cur === thuKey) break
    cur = addDays(cur, 1)
  }

  const slotIndex = new Map<string, number>(SLOT_MINUTES.map((s, i) => [`${s.hh}:${s.mm}`, i]))
  const latestBySlot = new Map<string, { t: number; v: number; raw: EquitySnapshot }>()

  for (const it of items) {
    if (typeof it?.ts_utc !== 'string') continue
    const p = kstPartsFromIso(it.ts_utc)
    if (!p) continue
    if (p.mm % 10 !== 0) continue
    // 10분 스냅샷 슬롯에 없는 시각은 제외 (22:30~05:00)
    const si = slotIndex.get(`${p.hh}:${p.mm}`)
    if (si == null) continue

    // 22:30~23:59는 해당 날짜 세션, 00:00~05:00는 전날 세션으로 귀속
    const kstYmd = ymd(p.y, p.m, p.d)
    const sessionYmd = (p.hh === 22 || p.hh === 23) ? kstYmd : addDays(kstYmd, -1)
    if (sessionYmd < startKey || sessionYmd > thuKey) continue

    const v = valueOf(it, metric)
    if (v == null) continue

    const t = new Date(it.ts_utc).getTime()
    const key = `${sessionYmd}|${p.hh}:${p.mm}`
    const prev = latestBySlot.get(key)
    if (!prev || t > prev.t) latestBySlot.set(key, { t, v, raw: it })
  }

  const points: SlotPoint[] = []
  sessions.forEach((sessionYmd, si) => {
    SLOT_MINUTES.forEach((s, slotI) => {
      const key = `${sessionYmd}|${s.hh}:${s.mm}`
      const got = latestBySlot.get(key)
      points.push({
        x: si * SLOT_MINUTES.length + slotI,
        sessionYmd,
        hh: s.hh,
        mm: s.mm,
        v: got ? got.v : null,
        raw: got?.raw,
      })
    })
  })

  return { points, sessions }
}

const MARGIN = { top: 16, right: 16, bottom: 84, left: 80 }
const BASE_W = 920
const H = 420
const Y_TICKS = 5

type Series = ReturnType<typeof toSeries>

function buildChart(series: Series, metric: Metric, width: number) {
  if (series.points.length < 2) return null
  const IW = width - MARGIN.left - MARGIN.right
  const IH = H - MARGIN.top - MARGIN.bottom

  const values = series.points.map((s) => s.v).filter((v): v is number => v != null && isFinite(v))
  if (values.length < 1) return null

  const rawMin = Math.min(...values)
  const rawMax = Math.max(...values)
  const padding = (rawMax - rawMin) * 0.12 || Math.abs(rawMax) * 0.05 || 1
  const yMin = rawMin - padding
  const yMax = rawMax + padding
  const ySpan = yMax - yMin

  const xCount = series.points.length
  const toX = (i: number) => (i / Math.max(1, xCount - 1)) * IW
  const toY = (v: number) => IH - ((v - yMin) / ySpan) * IH

  // null 구간은 끊어서 여러 segment로 렌더링
  const segments: { linePath: string; fillPath: string; lastX: number; lastY: number }[] = []
  let cur: { xs: number[]; ys: number[] } | null = null
  const flush = () => {
    if (!cur || cur.xs.length < 1) { cur = null; return }
    if (cur.xs.length === 1) { cur.xs.push(cur.xs[0]! + 2); cur.ys.push(cur.ys[0]!) }
    const c = cur
    const linePath = c.xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${c.ys[i]!.toFixed(1)}`).join(' ')
    const lastX = c.xs[c.xs.length - 1] ?? 0
    const lastY = c.ys[c.ys.length - 1] ?? 0
    const fillPath = `${linePath} L${lastX.toFixed(1)},${IH} L${c.xs[0]!.toFixed(1)},${IH} Z`
    segments.push({ linePath, fillPath, lastX, lastY })
    cur = null
  }

  series.points.forEach((p, i) => {
    if (p.v == null || !isFinite(p.v)) { flush(); return }
    if (!cur) cur = { xs: [], ys: [] }
    cur.xs.push(toX(i))
    cur.ys.push(toY(p.v))
  })
  flush()

  // Y 그리드 + 레이블
  const yTicks = Array.from({ length: Y_TICKS }, (_, i) => {
    const v = yMin + (ySpan * i) / (Y_TICKS - 1)
    return { v, y: toY(v), label: fmtYLabel(v, metric) }
  })

  const dayTicks = series.sessions.map((sessionYmd, si) => {
    const startIdx = si * SLOT_MINUTES.length
    const endIdx = startIdx + SLOT_MINUTES.length - 1
    const midIdx = Math.round((startIdx + endIdx) / 2)
    const sepX = si > 0 ? toX(startIdx) : null
    const { day, date } = fmtDayLabel(sessionYmd)
    return { midX: toX(midIdx), sepX, day, date, sessionYmd }
  })

  const hourTicks = series.points
    .map((p, i) => ({ x: toX(i), idx: i, label: fmtSlotLabelKst(p.hh, p.mm), hasData: p.v != null && isFinite(p.v) }))
    .filter((t) => t.hasData)

  const lastPoint = [...series.points].reverse().find((p) => p.v != null && isFinite(p.v as number)) ?? null
  const lineColor = metric === 'assets'
    ? theme.accentCyan
    : (lastPoint?.v ?? 0) >= 0 ? theme.positive : theme.negative

  return { segments, yTicks, dayTicks, hourTicks, lineColor, width, IW, IH }
}

export default function EquityChartModal({
  open, title, metric, items, loading, onClose,
}: {
  open: boolean
  title: string
  metric: Metric
  items: EquitySnapshot[]
  loading?: boolean
  onClose: () => void
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const series = useMemo(() => toSeries(items, metric), [items, metric])
  const chartWidth = useMemo(() => {
    // 포인트 수가 늘어나면 가로로 길어지게(스크롤로 탐색)
    const pxPerPoint = 14
    const w = MARGIN.left + MARGIN.right + Math.max(1, series.points.length - 1) * pxPerPoint
    return Math.max(BASE_W, w)
  }, [series.points.length])
  const chart = useMemo(() => buildChart(series, metric, chartWidth), [series, metric, chartWidth])
  const last = useMemo(() => {
    const pts = series.points
    for (let i = pts.length - 1; i >= 0; i--) {
      const r = pts[i]?.raw
      if (r) return r
    }
    return null
  }, [series.points])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0, zIndex: 9999,
        display: 'grid', placeItems: 'center', padding: 18,
        background: 'rgba(2,6,23,0.55)',
        backdropFilter: 'blur(10px)',
      }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        width: 'min(980px, 96vw)', maxHeight: 'min(84vh, 860px)',
        borderRadius: theme.radiusLg, overflow: 'hidden',
        border: '1px solid rgba(148,163,184,0.18)',
        boxShadow: '0 24px 80px rgba(0,0,0,0.45)',
        background: '#fff',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* 헤더 */}
        <div style={{
          padding: '12px 14px', background: theme.primary,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10,
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontFamily: theme.fontDisplay, fontSize: 14, fontWeight: 900, color: '#fff', letterSpacing: '-0.02em' }}>
              {title}
            </div>
            <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(226,232,240,0.85)' }}>
              {loading ? '로딩…' : `${series.points.length}pt · KST 22:30~05:00 (10분 스냅샷)`}
            </div>
          </div>
          <button
            type="button" onClick={onClose}
            style={{
              width: 34, height: 34, borderRadius: 12,
              border: '1px solid rgba(255,255,255,0.18)',
              background: 'rgba(255,255,255,0.14)',
              color: '#fff', fontSize: 16, fontWeight: 900, cursor: 'pointer',
            }}
            aria-label="닫기" title="닫기 (Esc)"
          >×</button>
        </div>

        {/* 본문 */}
        <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <div style={{ fontSize: 12, color: theme.onSurfaceVariant }}>
              표시 범위: 이번 주 월~목 · KST 22:30~05:00 10분 단위
            </div>
            {last && (
              <div style={{ fontSize: 12, color: theme.onSurface, fontVariantNumeric: 'tabular-nums' }}>
                최신{' '}
                {metric === 'assets'
                  ? `$${fmtMoney(last.total_assets_usd)}`
                  : metric === 'seed_return'
                  ? fmtPct(last.seed_return_pct ?? 0)
                  : fmtPct(last.total_return_pct)}
              </div>
            )}
          </div>

          <div style={{
            borderRadius: 16,
            border: '1px solid rgba(148,163,184,0.18)',
            background: '#fff',
            padding: 12,
          }}>
            {!chart ? (
              <div style={{ color: theme.onSurfaceVariant, fontSize: 13, padding: '20px 0' }}>
                이번 주 스냅샷이 아직 없습니다. (KST 22:30~05:00 10분 단위 기록)
              </div>
            ) : (
              <div style={{ width: '100%', overflowX: 'auto', overflowY: 'hidden' }}>
                <svg
                  width={chart.width}
                  height={H}
                  viewBox={`0 0 ${chart.width} ${H}`}
                  preserveAspectRatio="none"
                  aria-hidden
                  style={{ display: 'block' }}
                >
                  <defs>
                    <linearGradient id="chartFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chart.lineColor} stopOpacity={0.18} />
                      <stop offset="100%" stopColor={chart.lineColor} stopOpacity={0.02} />
                    </linearGradient>
                    <clipPath id="chartClip">
                      <rect x={0} y={0} width={chart.IW} height={chart.IH} />
                    </clipPath>
                  </defs>

                  <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
                  {/* Y 그리드 + 레이블 */}
                  {chart.yTicks.map((t, i) => (
                    <g key={i}>
                      <line x1={0} y1={t.y} x2={chart.IW} y2={t.y}
                        stroke="rgba(15,23,42,0.12)" strokeWidth={1} strokeDasharray="4 4" />
                      <text x={-10} y={t.y} textAnchor="end" dominantBaseline="middle"
                        fill="rgba(15,23,42,0.70)" fontSize={11} fontFamily="monospace">
                        {t.label}
                      </text>
                    </g>
                  ))}

                  {/* X 그리드 (시간 단위) */}
                  {chart.hourTicks.map((t) => (
                    <line
                      key={`xg-${t.idx}`}
                      x1={t.x}
                      y1={0}
                      x2={t.x}
                      y2={chart.IH}
                      stroke="rgba(15,23,42,0.06)"
                      strokeWidth={1}
                    />
                  ))}

                  {/* X 축 선 */}
                  <line x1={0} y1={chart.IH} x2={chart.IW} y2={chart.IH} stroke="rgba(15,23,42,0.25)" strokeWidth={1} />
                  {/* Y 축 선 */}
                  <line x1={0} y1={0} x2={0} y2={chart.IH} stroke="rgba(15,23,42,0.25)" strokeWidth={1} />

                  {/* 날짜 구분선 + 요일 레이블 */}
                  {chart.dayTicks.map((t, i) => (
                    <g key={i}>
                      {/* 날짜 경계 구분선 */}
                      {t.sepX != null && (
                        <line x1={t.sepX} y1={0} x2={t.sepX} y2={chart.IH}
                          stroke="rgba(15,23,42,0.18)" strokeWidth={1} strokeDasharray="2 4" />
                      )}
                      {/* 요일 */}
                      <text x={t.midX} y={chart.IH + 16} textAnchor="middle"
                        fill="rgba(15,23,42,0.85)" fontSize={12} fontWeight={800} fontFamily="sans-serif">
                        {t.day}
                      </text>
                      {/* 날짜 (M/D) */}
                      <text x={t.midX} y={chart.IH + 30} textAnchor="middle"
                        fill="rgba(15,23,42,0.55)" fontSize={10} fontFamily="monospace">
                        {t.date}
                      </text>
                    </g>
                  ))}

                  {/* 시간 레이블 (10분 단위, 90도 회전) */}
                  {chart.hourTicks.map((t) => (
                    <text
                      key={`xh-${t.idx}`}
                      x={t.x}
                      y={chart.IH + 80}
                      textAnchor="end"
                      fill="rgba(15,23,42,0.55)"
                      fontSize={9}
                      fontFamily="monospace"
                      transform={`rotate(90, ${t.x}, ${chart.IH + 80})`}
                    >
                      {t.label}
                    </text>
                  ))}

                  {/* 클립 그룹 */}
                  <g clipPath="url(#chartClip)">
                    {chart.segments.map((s, idx) => (
                      <g key={idx}>
                        <path d={s.fillPath} fill="url(#chartFill)" />
                        <path d={s.linePath} fill="none" stroke={chart.lineColor}
                          strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
                        <circle cx={s.lastX} cy={s.lastY} r={4}
                          fill={chart.lineColor} stroke="rgba(255,255,255,0.95)" strokeWidth={2} />
                      </g>
                    ))}
                  </g>
                </g>
                </svg>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
