export const indicators = [
  { id: 'cpi', name: 'CPI (YoY)', region: 'US', value: '3.0%', prev: '3.2%', date: '2026-04-10', trend: 'down' as const },
  { id: 'pce', name: 'PCE 물가', region: 'US', value: '2.6%', prev: '2.7%', date: '2026-04-28', trend: 'down' as const },
  { id: 'nfp', name: '비농업 고용', region: 'US', value: '+185K', prev: '+172K', date: '2026-05-02', trend: 'up' as const },
  { id: 'ffr', name: '연준 기준금리', region: 'US', value: '4.25–4.50%', prev: '동일', date: '2026-05-01', trend: 'flat' as const },
  { id: 'pmi', name: '제조업 ISM PMI', region: 'US', value: '50.3', prev: '49.8', date: '2026-05-01', trend: 'up' as const },
  { id: 'vix', name: 'VIX', region: 'Global', value: '16.4', prev: '18.1', date: '2026-05-04', trend: 'down' as const },
]
