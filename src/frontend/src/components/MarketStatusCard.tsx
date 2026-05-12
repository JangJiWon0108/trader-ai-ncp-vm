import { useEffect, useMemo, useState } from 'react'
import { theme } from '../theme'

type UsMarketStatus = {
  nyLabel: string
  kstLabel: string
  regularHoursLabel: string
  isRegularOpen: boolean
  stateLabel: string
  hintPrefix: string
  hintDuration: string
}

const NY_TZ = 'America/New_York'
const KST_TZ = 'Asia/Seoul'

function pad2(n: number) {
  return String(n).padStart(2, '0')
}

function formatDuration(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${h}시간 ${m}분 ${s}초`
  if (m > 0) return `${m}분 ${s}초`
  return `${s}초`
}

type ZonedParts = {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
  weekdayShort: string
  offsetMinutes: number
}

function parseGmtOffsetToMinutes(offset: string) {
  // e.g. "GMT-4", "GMT-04:00", "UTC-4"
  const cleaned = offset.replace('UTC', 'GMT')
  const m = cleaned.match(/^GMT([+-])(\d{1,2})(?::?(\d{2}))?$/)
  if (!m) return 0
  const sign = m[1] === '-' ? -1 : 1
  const hh = Number(m[2] ?? 0)
  const mm = Number(m[3] ?? 0)
  return sign * (hh * 60 + mm)
}

function getZonedParts(timeZone: string, now: Date): ZonedParts {
  const fmt = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    weekday: 'short',
    timeZoneName: 'shortOffset',
  })

  const parts = fmt.formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value

  const year = Number(get('year'))
  const month = Number(get('month'))
  const day = Number(get('day'))
  const hour = Number(get('hour'))
  const minute = Number(get('minute'))
  const second = Number(get('second'))
  const weekdayShort = String(get('weekday') ?? '')
  const tzOffset = String(get('timeZoneName') ?? 'GMT+0').replace(/\s/g, '')
  const offsetMinutes = parseGmtOffsetToMinutes(tzOffset)

  return { year, month, day, hour, minute, second, weekdayShort, offsetMinutes }
}

function formatZonedClock(timeZone: string, now: Date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(now)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00'
  return `${get('hour')}:${get('minute')}:${get('second')}`
}

function zonedTimeToUtcMs(z: Pick<ZonedParts, 'year' | 'month' | 'day' | 'offsetMinutes'>, hh: number, mm: number, ss = 0) {
  // local time in zone -> UTC timestamp using zone offset at "now"
  const utcAsIf = Date.UTC(z.year, z.month - 1, z.day, hh, mm, ss, 0)
  return utcAsIf - z.offsetMinutes * 60_000
}

function computeUsMarketStatus(now: Date): UsMarketStatus {
  const ny = getZonedParts(NY_TZ, now)
  const kstClock = formatZonedClock(KST_TZ, now)

  const isWeekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(ny.weekdayShort)

  const nowUtc = now.getTime()
  const openUtc = zonedTimeToUtcMs(ny, 9, 30, 0)
  const closeUtc = zonedTimeToUtcMs(ny, 16, 0, 0)

  const isDst = ny.offsetMinutes === -240
  const regularHoursLabel = isDst ? '정규장 22:30 – 05:00 (KST, 서머타임)' : '정규장 23:30 – 06:00 (KST)'

  const isRegularOpen = isWeekday && nowUtc >= openUtc && nowUtc < closeUtc

  let hintPrefix = ''
  let hintDuration = ''
  if (isRegularOpen) {
    hintPrefix = '마감까지'
    hintDuration = formatDuration(closeUtc - nowUtc)
  } else if (isWeekday && nowUtc < openUtc) {
    hintPrefix = '개장까지'
    hintDuration = formatDuration(openUtc - nowUtc)
  } else {
    // 다음 개장(대략: 다음 평일 09:30) — 휴장일(공휴일)은 미반영
    // NY 캘린더 날짜를 UTC 기준으로 하루씩 증가시키며 평일 찾기
    let d = new Date(Date.UTC(ny.year, ny.month - 1, ny.day, 12, 0, 0, 0))
    do {
      d = new Date(d.getTime() + 86_400_000)
      const probe = getZonedParts(NY_TZ, d)
      if (['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(probe.weekdayShort)) {
        const nextOpenUtc = zonedTimeToUtcMs(probe, 9, 30, 0)
        hintPrefix = '다음 개장까지'
        hintDuration = formatDuration(nextOpenUtc - nowUtc)
        break
      }
    } while (true)
  }

  const nyLabel = `${pad2(ny.hour)}:${pad2(ny.minute)}:${pad2(ny.second)}`
  const stateLabel = isRegularOpen ? '장중' : '장외'

  return {
    nyLabel,
    kstLabel: kstClock,
    regularHoursLabel,
    isRegularOpen,
    stateLabel,
    hintPrefix,
    hintDuration,
  }
}

export default function MarketStatusCard() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [])

  const status = useMemo(() => computeUsMarketStatus(now), [now])

  const dot = status.isRegularOpen ? theme.positive : '#94a3b8'
  const badgeBg = status.isRegularOpen ? theme.positiveBg : 'rgba(148, 163, 184, 0.12)'
  const badgeBorder = status.isRegularOpen ? 'rgba(16, 185, 129, 0.25)' : 'rgba(148, 163, 184, 0.22)'
  const badgeText = status.isRegularOpen ? '#34d399' : '#cbd5e1'

  return (
    <div
      className="sidebar-foot"
      style={{
        margin: '0 18px 12px',
        padding: 14,
        borderRadius: theme.radiusMd,
        background: 'rgba(15, 23, 42, 0.65)',
        border: '1px solid rgba(148, 163, 184, 0.15)',
        fontFamily: theme.fontSans,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          <span
            aria-hidden
            style={{
              width: 9,
              height: 9,
              borderRadius: 999,
              background: dot,
              boxShadow: `0 0 16px ${dot}`,
              flexShrink: 0,
            }}
          />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '-0.01em', color: '#e2e8f0' }}>
              미국 정규장
            </div>
            <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.35 }}>
              <div style={{ whiteSpace: 'normal', wordBreak: 'keep-all' }}>{status.regularHoursLabel}</div>
              <div style={{ marginTop: 4 }}>
                <div style={{ wordBreak: 'keep-all' }}>{status.hintPrefix}</div>
                <div
                  style={{
                    marginTop: 2,
                    fontWeight: 700,
                    color: '#cbd5e1',
                    fontVariantNumeric: 'tabular-nums',
                    wordBreak: 'keep-all',
                    whiteSpace: 'normal',
                  }}
                >
                  {status.hintDuration}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 10px',
            borderRadius: 999,
            background: badgeBg,
            border: `1px solid ${badgeBorder}`,
            color: badgeText,
            fontSize: 12,
            fontWeight: 800,
            letterSpacing: '-0.01em',
            flexShrink: 0,
          }}
          title="정규장 여부(뉴욕 09:30~16:00)를 기준으로 계산합니다. 공휴일 휴장은 미반영."
        >
          {status.stateLabel}
        </div>
      </div>

      <div style={{ marginTop: 12, display: 'grid', gap: 10 }}>
        <div
          style={{
            padding: '10px 12px',
            borderRadius: 14,
            background: 'rgba(2, 6, 23, 0.55)',
            border: '1px solid rgba(148, 163, 184, 0.12)',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#818cf8', marginBottom: 6 }}>
            NEW YORK
          </div>
          <div style={{ fontSize: 16, fontWeight: 900, color: '#e2e8f0', fontVariantNumeric: 'tabular-nums', letterSpacing: '0.02em' }}>
            {status.nyLabel}
          </div>
        </div>

        <div
          style={{
            padding: '10px 12px',
            borderRadius: 14,
            background: 'rgba(2, 6, 23, 0.55)',
            border: '1px solid rgba(148, 163, 184, 0.12)',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', color: '#38bdf8', marginBottom: 6 }}>
            KST
          </div>
          <div style={{ fontSize: 16, fontWeight: 900, color: '#e2e8f0', fontVariantNumeric: 'tabular-nums', letterSpacing: '0.02em' }}>
            {status.kstLabel}
          </div>
        </div>
      </div>
    </div>
  )
}

