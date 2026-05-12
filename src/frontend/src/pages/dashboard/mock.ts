export const summaryCards = [
  {
    id: 'equity',
    title: '총 자산',
    value: '$128,430.52',
    changePct: 1.24,
    spark: [0.4, 0.42, 0.38, 0.45, 0.5, 0.48, 0.55, 0.58, 0.62, 0.6, 0.68],
  },
  {
    id: 'day',
    title: '오늘 손익',
    value: '+$1,582.10',
    changePct: 1.24,
    spark: [0.55, 0.52, 0.58, 0.6, 0.57, 0.62, 0.65, 0.63, 0.7, 0.72, 0.78],
  },
  {
    id: 'cash',
    title: '가용 현금',
    value: '$12,400.00',
    changePct: 0,
    spark: [0.7, 0.7, 0.69, 0.71, 0.7, 0.72, 0.71, 0.73, 0.72, 0.74, 0.73],
  },
]

export const aiFeed = [
  {
    id: '1',
    time: '09:42',
    title: 'NVDA — 거래량 급증',
    body: 'AI 코파일럿: 단기 모멘텀 상승 구간. 기존 포지션 유지 권고.',
    ai: true,
  },
  {
    id: '2',
    time: '08:15',
    title: 'FOMC 회의록 공개',
    body: '시장 뉴스: 금리 인하 기대 완화. 방어적 섹터 관심 증가.',
    ai: false,
  },
  {
    id: '3',
    time: '전일',
    title: 'MSFT — 목표가 상향',
    body: 'AI 코파일럿: 클라우드 성장률 반영. 중기 매수 신호 유지.',
    ai: true,
  },
]

export const watchlist = [
  { symbol: 'AAPL', name: 'Apple', price: 189.42, chg: 0.82 },
  { symbol: 'MSFT', name: 'Microsoft', price: 378.91, chg: -0.21 },
  { symbol: 'GOOGL', name: 'Alphabet', price: 141.2, chg: 1.05 },
  { symbol: 'AMZN', name: 'Amazon', price: 178.33, chg: 0.44 },
]
