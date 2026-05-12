export function kstYmd(date: Date) {
  const s = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
  return s
}

export function kstTodayYmd() {
  return kstYmd(new Date())
}

export function kstYesterdayYmd() {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return kstYmd(d)
}

export function pretty(obj: unknown) {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

