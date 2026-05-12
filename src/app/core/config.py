"""
애플리케이션 설정 (Pydantic Settings).

.env 로드 후 KIS·Supabase·스케줄·매매 임계값·텔레그램·Upstage 등 런타임 상수를 한곳에서 제공한다.
`settings` 싱글톤이 라우트·서비스에서 임포트된다.
"""

# ─── 모듈 임포트 ───
import os
import unicodedata
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# ─── 설정 로드 ───

load_dotenv()


# ─── 스키마 정의 ───


class Settings(BaseSettings):
    PROJECT_NAME: str = Field(..., description="프로젝트 이름")
    PROJECT_DESCRIPTION: str = Field(..., description="프로젝트 설명")
    PROJECT_VERSION: str = Field(..., description="프로젝트 버전")

    DEBUG: bool = Field(..., description="디버그 모드 활성화 여부")

    CORS_ORIGINS: List[str] = Field(..., description="CORS allow_origins (예: [\"*\"] 또는 [\"http://localhost:5173\"])")

    SUPABASE_URL: str = Field(..., description="Supabase URL")
    SUPABASE_KEY: str = Field(..., description="Supabase anon/publishable key")
    SUPABASE_SERVICE_KEY: str = Field(..., description="Supabase service role key")

    # 추론(run_inference 등): model_meta.json·keras·스케일러가 있는 디렉터리
    # 프로젝트 루트 기준 상대경로 또는 절대경로 (예: predict_model/model/v7_260511_최근30일_validation_주기5일)
    PREDICT_MODEL_DIR: str = Field(
        ...,
        description="Transformer 추론 모델 디렉터리",
    )

    ML_SERVICE_URL: str = Field(
        "",
        description="Cloud Run ML 서비스(trader-ai-ml) 베이스 URL. 비우면 로컬 프로세스에서 run_inference 직접 실행",
    )
    ML_SERVICE_AUTH_TOKEN: str = Field(
        "",
        description="ML 서비스 호출 인증(선택). ML 컨테이너 ML_INFERENCE_AUTH_TOKEN 과 동일 값",
    )

    # 한국투자증권 — 모의투자 전용 (.env 의 KIS_MOCK_* 만 사용)
    KIS_MOCK_BASE_URL: str = Field(
        ...,
        description="모의투자 API 베이스 URL",
    )
    KIS_MOCK_APPKEY: str = Field(..., description="모의투자 앱키")
    KIS_MOCK_APPSECRET: str = Field(..., description="모의투자 앱시크릿")
    KIS_MOCK_CANO: str = Field(..., description="모의 계좌번호 앞 8자리")
    KIS_MOCK_ACNT_PRDT_CD: str = Field(..., description="모의 계좌상품코드 뒤 2자리")

    # 한국투자증권 — 실전투자 전용 (.env 의 KIS_REAL_* 만 사용)
    KIS_REAL_BASE_URL: str = Field(
        ...,
        description="실전투자 API 베이스 URL",
    )
    KIS_REAL_APPKEY: str = Field(..., description="실전 앱키")
    KIS_REAL_APPSECRET: str = Field(..., description="실전 앱시크릿")
    KIS_REAL_CANO: str = Field(..., description="실전 계좌번호 앞 8자리")
    KIS_REAL_ACNT_PRDT_CD: str = Field(..., description="실전 계좌상품코드 뒤 2자리")

    KIS_USE_MOCK: bool = Field(..., description="true면 모의 블록, false면 실전 블록")

    SCHEDULE_AUTO_BUY_TIME: str = Field(..., description="자동 매수 실행 시간 (HH:MM, KST)")
    SCHEDULE_AUTO_SELL_INTERVAL_MIN: int = Field(..., description="자동 매도 체크 주기 (분)")
    SCHEDULE_ECONOMIC_UPDATE_TIME: str = Field(..., description="경제 데이터 수집 시간 (HH:MM, KST)")
    STARTUP_RUN_AUTO_BUY: bool = Field(
        ...,
        description="서버 시작 시 자동 매수 1회 즉시 실행 여부",
    )
    SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE: bool = Field(
        ...,
        description="매일 경제·주가 DB 갱신(스케줄) 직후, 신규 저장 행이 있으면 저장 모델로 추론·predicted_stocks 등 갱신",
    )
    SCHEDULER_MINUTE_LOG_TO_SUPABASE: bool = Field(
        ...,
        description="True일 때만 auto_sell 분 요약을 Supabase scheduler_minute_logs 에 저장(테이블·RLS 준비 후 켜기)",
    )

    # ── 매수/매도 주문 기본값 ──────────────────────────────────────────────────
    TRADING_BUY_PCT_OF_CASH: float = Field(0.10, description="초기 시드 대비 종목당 매수 비율 (0~1). 예: 0.10 = 10%")
    TRADING_MAX_POSITIONS: int = Field(..., description="최대 동시 보유 종목 수")
    TRADING_ORDER_TYPE: str = Field(..., description="주문 유형 (00: 지정가, 01: 시장가)")

    # ── 기술적 지표 파라미터 ──────────────────────────────────────────────────
    TECH_LOOKBACK_DAYS: int = Field(..., description="기술적 지표 계산에 사용할 과거 데이터 기간 (일)")
    TECH_SMA_SHORT: int = Field(..., description="단기 이동평균 기간 (골든크로스 기준)")
    TECH_SMA_LONG: int = Field(..., description="장기 이동평균 기간 (골든크로스 기준)")
    TECH_RSI_PERIOD: int = Field(..., description="RSI 계산 기간")
    TECH_MACD_SHORT: int = Field(..., description="MACD 단기 EMA 기간")
    TECH_MACD_LONG: int = Field(..., description="MACD 장기 EMA 기간")
    TECH_MACD_SIGNAL: int = Field(..., description="MACD 시그널 EMA 기간")

    # ── 매수 조건 임계값 ──────────────────────────────────────────────────────
    BUY_MODEL_ACCURACY_MIN: float = Field(..., description="매수 허용 최소 모델 정확도 (%)")
    BUY_RISE_PROB_MIN: float = Field(..., description="매수 허용 최소 상승 확률 (%)")
    BUY_RSI_MAX: float = Field(..., description="매수 허용 RSI 상한 (이 값 미만일 때 매수 신호)")
    BUY_SENTIMENT_MIN: float = Field(..., description="매수 허용 최소 감성 점수")
    BUY_TECH_MIN_WITH_SENTIMENT: int = Field(..., description="감성 조건 충족 시 필요한 최소 기술지표 매수 신호 수")
    BUY_TECH_MIN_WITHOUT_SENTIMENT: int = Field(..., description="감성 데이터 없을 때 필요한 최소 기술지표 매수 신호 수")
    BUY_SCORE_WEIGHT_RISE_PROB: float = Field(..., description="종합점수 가중치 — 상승확률")
    BUY_SCORE_WEIGHT_TECH: float = Field(..., description="종합점수 가중치 — 기술지표")
    BUY_SCORE_WEIGHT_SENTIMENT: float = Field(..., description="종합점수 가중치 — 감성점수")
    BUY_SCORE_WEIGHT_GOLDEN_CROSS: float = Field(..., description="기술지표 점수 내 골든크로스 가중치")
    BUY_SCORE_WEIGHT_RSI: float = Field(..., description="기술지표 점수 내 RSI 가중치")
    BUY_SCORE_WEIGHT_MACD: float = Field(..., description="기술지표 점수 내 MACD 가중치")

    # ── 매도 조건 임계값 ──────────────────────────────────────────────────────
    SELL_TAKE_PROFIT_PCT: float = Field(..., description="익절 기준 수익률 (%)")
    SELL_STOP_LOSS_PCT: float = Field(..., description="손절 기준 수익률 (%, 음수)")
    SELL_RSI_OVERBOUGHT: float = Field(..., description="과매수 판단 RSI 기준 (이 값 초과 시 매도 신호)")
    SELL_SENTIMENT_MAX: float = Field(..., description="부정 감성 판단 기준 (이 값 미만 시 매도 신호)")
    SELL_TECH_MIN_WITH_SENTIMENT: int = Field(..., description="부정 감성 충족 시 필요한 최소 기술지표 매도 신호 수")
    SELL_TECH_MIN_TECH_ONLY: int = Field(..., description="감성과 무관하게(또는 감성이 중립/긍정일 때) 적용하는 기술지표 기반 매도 최소 신호 수")
    SELL_TECH_MIN_WITHOUT_SENTIMENT: int = Field(..., description="감성 데이터가 없을 때 적용하는 기술지표 기반 매도 최소 신호 수")

    # ── 뉴스 감성 분석 파라미터 ───────────────────────────────────────────────
    SENTIMENT_RELEVANCE_THRESHOLD: float = Field(..., description="뉴스 기사 관련성 최소 점수 (이 값 미만 기사 제외)")
    SENTIMENT_LOOKBACK_DAYS: int = Field(..., description="뉴스 감성 분석 대상 기간 (일)")

    # ── 텔레그램 알림 (alarm/telegram.py) ─────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = Field(..., description="텔레그램 봇 HTTP API 토큰")
    TELEGRAM_CHAT_ID: str = Field(
        ...,
        description="알림 수신 chat_id (봇에게 /start 후 getUpdates 등으로 확인)",
    )
    TELEGRAM_MESSAGE_PREFIX: str = Field(
        "",
        description="텔레그램 메시지 접두사(예: [Trader-AI]). 비우면 PROJECT_NAME 기반으로 자동 생성",
    )

    # ── Upstage LLM (OpenAI 호환) ────────────────────────────────────────────
    UPSTAGE_BASE_URL: str = Field(
        "https://api.upstage.ai/v1",
        description="Upstage OpenAI 호환 API base_url",
    )
    UPSTAGE_MODEL_ID: str = Field(
        "solar-pro",
        description="Upstage 기본 모델 ID (chat.completions)",
    )
    UPSTAGE_API_KEY: str = Field(
        "",
        description="Upstage API 키",
    )

    EOD_LLM_UPSTAGE_MODEL_ID: str = Field(
        "",
        description="일일 마감 요약 리포트 생성에 사용할 Upstage 모델 ID (비우면 UPSTAGE_MODEL_ID 사용)",
    )

    SCHEDULE_EOD_LLM_REPORT_ENABLED: bool = Field(
        ...,
        description="Upstage 일일 마감 리포트를 텔레그램으로 보낼지 여부",
    )
    SCHEDULE_EOD_LLM_REPORT_TIME_KST: str = Field(
        ...,
        description="일일 LLM 리포트 실행 시각 (KST HH:MM, SCHEDULE_AUTO_BUY_TIME 과 동일한 schedule 로컬 기준)",
    )

    FRED_API_KEY: str = Field(..., description="FRED API 키")

    ALPHA_VANTAGE_API_KEY_MAIN: str = Field(..., description="Alpha Vantage API 키(main)")
    ALPHA_VANTAGE_API_KEY_SUB_1: str = Field(..., description="Alpha Vantage API 키(sub1)")
    ALPHA_VANTAGE_API_KEY_SUB_2: str = Field(..., description="Alpha Vantage API 키(sub2)")

    @property
    def KIS_APPKEY(self) -> str:
        return self.KIS_MOCK_APPKEY if self.KIS_USE_MOCK else self.KIS_REAL_APPKEY

    @property
    def KIS_APPSECRET(self) -> str:
        return self.KIS_MOCK_APPSECRET if self.KIS_USE_MOCK else self.KIS_REAL_APPSECRET

    @property
    def KIS_CANO(self) -> str:
        return self.KIS_MOCK_CANO if self.KIS_USE_MOCK else self.KIS_REAL_CANO

    @property
    def KIS_ACNT_PRDT_CD(self) -> str:
        return self.KIS_MOCK_ACNT_PRDT_CD if self.KIS_USE_MOCK else self.KIS_REAL_ACNT_PRDT_CD

    @property
    def kis_base_url(self) -> str:
        """KIS_USE_MOCK 에 따라 모의 또는 실전 베이스 URL"""
        return self.KIS_MOCK_BASE_URL if self.KIS_USE_MOCK else self.KIS_REAL_BASE_URL

    @property
    def predict_model_path(self) -> Path:
        """PREDICT_MODEL_DIR 를 프로젝트 루트 기준으로 해석 (절대경로 그대로 사용)."""
        root = Path(__file__).resolve().parents[2]
        raw = unicodedata.normalize("NFD", (self.PREDICT_MODEL_DIR or "").strip())
        if not raw:
            raise ValueError("PREDICT_MODEL_DIR 가 비어 있습니다. (.env 설정 필요)")
        p = Path(raw)
        return p.resolve() if p.is_absolute() else (root / p).resolve()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
