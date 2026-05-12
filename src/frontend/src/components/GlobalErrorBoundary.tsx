import React from 'react'
import AlertModal from './AlertModal'

type Props = {
  children: React.ReactNode
}

type State = {
  hasError: boolean
  message: string
}

function safeMessage(err: unknown): string {
  if (err instanceof Error) return err.message || String(err)
  try {
    return typeof err === 'string' ? err : JSON.stringify(err)
  } catch {
    return String(err)
  }
}

export default class GlobalErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: safeMessage(error),
    }
  }

  componentDidCatch(error: unknown, info: unknown) {
    // 렌더 크래시는 사용자 복구가 최우선이라, 여기서는 콘솔 로깅만 best-effort.
    // (추후 Sentry 등 붙이면 여기에서 수집)
    try {
      // eslint-disable-next-line no-console
      console.error('[GlobalErrorBoundary] crash', error, info)
    } catch {
      // ignore
    }
  }

  private resetToHome = () => {
    // react-router 훅을 쓸 수 없는 클래스 컴포넌트이므로 간단히 pathname 이동
    try {
      window.location.assign('/')
    } catch {
      window.location.href = '/'
    }
  }

  private reload = () => {
    try {
      window.location.reload()
    } catch {
      window.location.href = window.location.href
    }
  }

  render() {
    if (!this.state.hasError) return this.props.children

    const msg = [
      '화면을 표시하는 중 오류가 발생했습니다.',
      '',
      '복구 방법을 선택해주세요.',
      '',
      `오류: ${this.state.message || '알 수 없는 오류'}`,
    ].join('\n')

    return (
      <AlertModal
        open
        kind="run"
        title="앱 크래시"
        message={msg}
        yesText="새로고침"
        noText="홈으로"
        onYes={this.reload}
        onNo={this.resetToHome}
        onClose={this.resetToHome}
      />
    )
  }
}

