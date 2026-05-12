export type Signal = 'buy' | 'hold' | 'sell'

export const picks = [
  {
    symbol: 'AMD',
    name: 'Advanced Micro Devices',
    signal: 'buy' as Signal,
    score: 82,
    target: 195.0,
    horizon: '4–8주',
    reason: '데이터센터 CPU 점유 확대, 밸류에이션 상대적 할인',
  },
  {
    symbol: 'META',
    name: 'Meta Platforms',
    signal: 'hold' as Signal,
    score: 64,
    target: 520.0,
    horizon: '8–12주',
    reason: '광고 회복 둔화 우려 · 기존 포지션 유지 구간',
  },
  {
    symbol: 'JPM',
    name: 'JPMorgan Chase',
    signal: 'buy' as Signal,
    score: 71,
    target: 218.0,
    horizon: '12주+',
    reason: '금리 환경 안정 시 은행주 수익 개선 시나리오',
  },
  {
    symbol: 'TSLA',
    name: 'Tesla',
    signal: 'sell' as Signal,
    score: 38,
    target: 165.0,
    horizon: '4주',
    reason: '변동성·밸류에이션 리스크, 리밸런싱 고려',
  },
]
