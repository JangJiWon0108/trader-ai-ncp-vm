/** 스케줄러 관리자 UI 공통 — ISO 시각 표시 */
export function fmtWhen(iso: string | null | undefined, timeZone: string) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('ko-KR', { timeZone, hour12: false })
  } catch {
    return iso
  }
}
