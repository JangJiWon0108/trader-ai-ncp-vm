import { useEffect, useState, type CSSProperties } from 'react'
import Card from '../../components/Card'
import PageHeader from '../../components/PageHeader'
import { theme } from '../../theme'
import { useAlert } from '../../contexts/AlertContext'
import {
  fetchAdminHealth,
  fetchAdminLogs,
  fetchAdminModelInfo,
  pingAdminKis,
  sendAdminTelegramTest,
} from '../../api'
import AdminActionButton from './components/AdminActionButton'
import EconomicLoadStatus from './components/EconomicLoadStatus'
import SentimentLoadStatus from './components/SentimentLoadStatus'
import InferenceLoadStatus from './components/InferenceLoadStatus'
import { pretty } from './components/statusUtils'
import LogViewerModal from './components/LogViewerModal'
import TradingInitializeAction from './components/TradingInitializeAction'
import ManualBuyAction from './components/ManualBuyAction'
import KisNowQuery from './components/KisNowQuery'
import EconomicSchedulerControl from './components/EconomicSchedulerControl'
import AutoBuySchedulerControl from './components/AutoBuySchedulerControl'
import AutoSellSchedulerControl from './components/AutoSellSchedulerControl'

const grid: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
  gap: theme.gutter,
}

export default function Admin() {
  const alert = useAlert()

  const [logLines, setLogLines] = useState(250)
  const [logsLoading, setLogsLoading] = useState(false)
  const [logsText, setLogsText] = useState<string | null>(null)
  const [logsError, setLogsError] = useState<string | null>(null)
  const [logsOpen, setLogsOpen] = useState(false)
  const [logsSource, setLogsSource] = useState<'file' | 'memory' | 'none' | null>(null)

  const [tgText, setTgText] = useState('')
  const [tgSending, setTgSending] = useState(false)

  const showBackendHealth = async () => {
    try {
      const data = await fetchAdminHealth()
      await alert.ok({
        title: '백엔드 상태',
        message: pretty(data),
      })
    } catch (e) {
      await alert.error({ title: '백엔드 상태', message: e instanceof Error ? e.message : String(e) })
    }
  }

  const showModelInfo = async () => {
    try {
      const data = await fetchAdminModelInfo()
      await alert.ok({
        title: '모델 경로/메타',
        message: pretty(data),
      })
    } catch (e) {
      await alert.error({ title: '모델 경로/메타', message: e instanceof Error ? e.message : String(e) })
    }
  }

  const runKisPing = async () => {
    try {
      const data = await pingAdminKis()
      await alert.ok({
        title: 'KIS 연결 테스트',
        message: pretty(data),
      })
    } catch (e) {
      await alert.error({ title: 'KIS 연결 테스트', message: e instanceof Error ? e.message : String(e) })
    }
  }

  const refreshLogs = async () => {
    setLogsLoading(true)
    setLogsError(null)
    try {
      const r = await fetchAdminLogs({ lines: logLines })
      setLogsText(r.text || '')
      setLogsSource(r.source ?? null)
    } catch (e) {
      setLogsError(e instanceof Error ? e.message : String(e))
      setLogsText(null)
      setLogsSource(null)
    } finally {
      setLogsLoading(false)
    }
  }

  const sendTelegramTest = async () => {
    const label = '텔레그램 전송'
    const ok = await alert.run({ title: label, message: `${label} 실행할까요?`, yesText: '전송', noText: '취소' })
    if (!ok) return
    setTgSending(true)
    try {
      const res = (await sendAdminTelegramTest(tgText.trim() || undefined)) as any
      if (res?.sent) {
        await alert.ok({ title: label, message: '전송 완료' })
      } else {
        await alert.warn({
          title: `${label} 실패`,
          message: `전송되지 않았습니다.\n\n사유: ${res?.error ?? '알 수 없음'}\n\n(서버 로그도 확인해주세요)`,
        })
      }
    } catch (e) {
      await alert.error({ title: `${label} 실패`, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setTgSending(false)
    }
  }

  const openLogs = async () => {
    setLogsOpen(true)
    await refreshLogs()
  }

  useEffect(() => {
    // 자동 폴링 제거: 사용자가 새로고침 버튼을 눌렀을 때만 요청
    // (lines 변경 시에는 모달을 다시 열거나 새로고침 버튼으로 반영)
  }, [])

  return (
    <div style={{ padding: theme.pagePadding, fontFamily: theme.fontSans, minHeight: '100%' }}>
      <PageHeader title="관리자" subtitle="버튼으로 테스트 호출 · 결과는 팝업/상태칩" />

      <LogViewerModal
        open={logsOpen}
        title="백엔드 로그"
        subtitle={`log/app.log · last ${logLines} lines${logsSource ? ` · ${logsSource}` : ''}`}
        text={logsText ?? ''}
        loading={logsLoading}
        onRefresh={refreshLogs}
        onClose={() => setLogsOpen(false)}
      />

      <div style={grid}>
        <Card title="테스트 버튼" subtitle="원하는 순간에만 호출하고 결과를 확인">
          <div style={{ display: 'grid', gap: 10 }}>
            <AdminActionButton
              title="백엔드 상태 확인"
              subtitle="health + 스케줄 오버뷰를 가져와서 결과를 팝업으로 표시"
              onClick={showBackendHealth}
              right={<span style={{ fontSize: 12, fontWeight: 900 }}>GET</span>}
            />
            <AdminActionButton
              title="모델 경로 확인"
              subtitle="현재 서버가 참조하는 모델 디렉터리/메타 확인"
              onClick={showModelInfo}
              right={<span style={{ fontSize: 12, fontWeight: 900 }}>GET</span>}
            />
            <AdminActionButton
              title="KIS 연결 테스트"
              subtitle="간단 호출로 토큰/네트워크/서명 정상 여부 확인"
              onClick={runKisPing}
              right={<span style={{ fontSize: 12, fontWeight: 900 }}>GET</span>}
            />
          </div>
        </Card>

        <Card title="KIS 현재조회" subtitle="가능한 한 많이 · 잔고/보유종목 필수 포함 · raw + 테이블">
          <KisNowQuery />
        </Card>

        <Card title="모의투자 초기화" subtitle="거래 상태(잔고/체결/미체결)만 재시작">
          <TradingInitializeAction />
        </Card>

        <Card title="수동 매수" subtitle="현재 기준으로 1회 실행 · 결과는 텔레그램으로 전송">
          <ManualBuyAction />
        </Card>

        <Card title="경제/주가 적재" subtitle="컴포넌트 단위로 확인/수동 수집">
          <EconomicLoadStatus />
        </Card>

        <Card title="알파밴티지 감성 적재" subtitle="적재 확인 + 수동 업데이트">
          <SentimentLoadStatus />
        </Card>

        <Card title="모델 추론/적재" subtitle="오늘 기준 완료 여부 + 수동 실행">
          <InferenceLoadStatus />
        </Card>

        <Card title="경제/주가 스케줄러" subtitle="경제·주가 일일 갱신 루프 · 서버 상태 조회 / 시작·중지·재시작">
          <EconomicSchedulerControl />
        </Card>

        <Card title="자동 매수 스케줄러" subtitle="일일 매수 잡 · 서버 상태 조회 / 시작·중지·재시작">
          <AutoBuySchedulerControl />
        </Card>

        <Card title="자동 매도 스케줄러" subtitle="장중 분 단위 점검 · 서버 상태 조회 / 시작·중지·재시작">
          <AutoSellSchedulerControl />
        </Card>

        <Card title="텔레그램 테스트" subtitle="샘플 메시지 전송">
          <div style={{ marginTop: 8, display: 'grid', gap: 10 }}>
            <div
              style={{
                borderRadius: theme.radiusLg,
                border: `1px solid ${theme.surfaceContainer}`,
                background: 'linear-gradient(180deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.02) 100%)',
                boxShadow: theme.shadow,
                padding: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 900, color: theme.onSurfaceVariant, letterSpacing: '0.02em' }}>
                  MESSAGE
                </div>
                <div style={{ fontSize: 11, color: theme.onSurfaceVariant }}>
                  비우면 기본 메시지 전송
                </div>
              </div>
              <textarea
                value={tgText}
                onChange={(e) => setTgText(e.target.value)}
                placeholder="예) 오늘 테스트 메시지입니다."
                rows={4}
                style={{
                  width: '100%',
                  resize: 'vertical',
                  minHeight: 96,
                  maxHeight: 220,
                  padding: '10px 12px',
                  borderRadius: 14,
                  border: `1px solid ${theme.outline}`,
                  background: 'rgba(2,6,23,0.35)',
                  color: theme.onSurface,
                  outline: 'none',
                  fontFamily: theme.fontSans,
                  lineHeight: 1.5,
                }}
              />
              <div style={{ marginTop: 8, fontSize: 11, color: theme.onSurfaceVariant, display: 'flex', justifyContent: 'space-between' }}>
                <span>Enter는 알럿 확인에 사용될 수 있어요.</span>
                <span>{tgText.length.toLocaleString('en-US')} chars</span>
              </div>
            </div>

            <AdminActionButton
              title="텔레그램 전송"
              subtitle="관리자 테스트 메시지를 텔레그램으로 전송"
              onClick={sendTelegramTest}
              tone="success"
              disabled={tgSending}
              right={<span style={{ fontSize: 12, fontWeight: 900 }}>POST</span>}
            />
          </div>
        </Card>

        <Card title="백엔드 로그" subtitle="log/app.log tail">
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', margin: '10px 0 12px', flexWrap: 'wrap' }}>
            <span style={{ color: theme.onSurfaceVariant, fontSize: 12, fontWeight: 800 }}>lines</span>
            <input
              type="number"
              min={50}
              max={3000}
              value={logLines}
              onChange={(e) => setLogLines(Math.max(50, Math.min(3000, parseInt(e.target.value || '250', 10))))}
              style={{
                width: 110,
                padding: '8px 10px',
                borderRadius: 10,
                border: `1px solid ${theme.surfaceContainer}`,
                background: 'rgba(255,255,255,0.03)',
                color: theme.onSurface,
                outline: 'none',
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
              }}
            />
            <button
              style={{
                appearance: 'none',
                border: `1px solid ${theme.outline}`,
                background: 'rgba(255,255,255,0.04)',
                color: theme.onSurface,
                borderRadius: 12,
                padding: '10px 12px',
                fontWeight: 900,
                fontSize: 13,
                cursor: 'pointer',
              }}
              onClick={openLogs}
              title="모달로 크게 보기"
            >
              자세히 보기
            </button>
          </div>

          {(logsLoading || logsError) && (
            <div style={{ marginTop: 8, fontSize: 12, color: logsError ? theme.negative : theme.onSurfaceVariant }}>
              {logsError ? `오류: ${logsError}` : '로딩 중…'}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

