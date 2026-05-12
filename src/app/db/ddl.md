-- ============================================================
-- 운영/로그 테이블 (건드리지 않음 - 데이터 보존)
-- ============================================================

create table public.access_tokens (
  id serial not null,
  access_token text not null,
  created_at timestamp with time zone null default CURRENT_TIMESTAMP,
  expiration_time timestamp with time zone not null,
  is_active boolean null default true,
  constraint access_tokens_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_access_tokens_expiration on public.access_tokens using btree (expiration_time) TABLESPACE pg_default;
create index IF not exists idx_access_tokens_created_at on public.access_tokens using btree (created_at) TABLESPACE pg_default;

create table public.balance_snapshots (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text null,
  holdings_count integer null,
  total_eval_usd numeric null,
  payload jsonb null,
  constraint balance_snapshots_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_balance_snapshots_date on public.balance_snapshots using btree (ny_trading_date) TABLESPACE pg_default;

create table public.daily_buy_logs (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text not null,
  success boolean null,
  status text null,
  candidate_count integer null,
  ordered_count integer null,
  payload jsonb null,
  telegram_sent boolean null,
  telegram_sent_at timestamp with time zone null,
  constraint daily_buy_logs_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_daily_buy_logs_date on public.daily_buy_logs using btree (ny_trading_date) TABLESPACE pg_default;

create table public.daily_buy_items (
  id bigint generated always as identity not null,
  run_id bigint null,
  ticker text null,
  stock_name text null,
  outcome text null,
  exchange_code text null,
  quantity integer null,
  limit_price numeric null,
  error text null,
  api_message text null,
  constraint daily_buy_items_pkey primary key (id),
  constraint daily_buy_items_run_id_fkey foreign KEY (run_id) references daily_buy_logs (id) on delete CASCADE
) TABLESPACE pg_default;

create table public.daily_economic_logs (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text null,
  success boolean null,
  status text null,
  updated_records integer null,
  error text null,
  payload jsonb null,
  telegram_sent boolean null,
  telegram_sent_at timestamp with time zone null,
  constraint daily_economic_logs_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_daily_economic_date on public.daily_economic_logs using btree (ny_trading_date) TABLESPACE pg_default;

create table public.daily_eod_llm_logs (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text not null,
  success boolean null,
  status text null,
  report_text text null,
  error text null,
  phase text null,
  telegram_sent boolean null,
  telegram_sent_at timestamp with time zone null,
  constraint daily_eod_llm_logs_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_daily_eod_llm_date on public.daily_eod_llm_logs using btree (ny_trading_date) TABLESPACE pg_default;

create table public.daily_inference_logs (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text null,
  success boolean null,
  status text null,
  error text null,
  payload jsonb null,
  telegram_sent boolean null,
  telegram_sent_at timestamp with time zone null,
  constraint daily_inference_logs_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_daily_inference_date on public.daily_inference_logs using btree (ny_trading_date) TABLESPACE pg_default;

create table public.order_history (
  id bigint generated always as identity not null,
  kst_at timestamp with time zone not null default now(),
  ny_trading_date text null,
  side text not null,
  ticker text not null,
  stock_name text null,
  exchange_code text null,
  quantity integer null,
  limit_price numeric null,
  order_type text null,
  rt_cd text null,
  api_message text null,
  success boolean null,
  source text null,
  payload jsonb null,
  constraint order_history_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_order_history_date on public.order_history using btree (ny_trading_date) TABLESPACE pg_default;
create index IF not exists idx_order_history_ticker on public.order_history using btree (ticker) TABLESPACE pg_default;

create table public.scheduler_minute_logs (
  id bigint generated always as identity not null,
  job_type text not null,
  kst_at timestamp with time zone not null default now(),
  ny_et_at timestamp with time zone null,
  ny_trading_date text null,
  market_hours boolean null,
  status text null,
  success boolean null,
  candidate_count integer null,
  payload jsonb null,
  telegram_sent boolean null,
  telegram_sent_at timestamp with time zone null,
  constraint scheduler_minute_logs_pkey primary key (id)
) TABLESPACE pg_default;

create table public.scheduler_minute_items (
  id bigint generated always as identity not null,
  run_id bigint null,
  ticker text null,
  stock_name text null,
  outcome text null,
  exchange_code text null,
  quantity integer null,
  limit_price numeric null,
  error text null,
  api_message text null,
  sell_reasons jsonb null,
  constraint scheduler_minute_items_pkey primary key (id),
  constraint scheduler_minute_items_run_id_fkey foreign KEY (run_id) references scheduler_minute_logs (id) on delete CASCADE
) TABLESPACE pg_default;


-- ============================================================
-- 주식/경제 데이터 테이블 (DROP → 재생성 대상)
-- ============================================================

-- 1. 경제 + 주가 데이터 (wide-format, 날짜별 1행)
CREATE TABLE public.economic_and_stock_data (
  날짜 date NOT NULL,
  -- 경제 지표
  "10년 기대 인플레이션율" numeric NULL,
  "장단기 금리차" numeric NULL,
  "기준금리" numeric NULL,
  "미시간대 소비자 심리지수" numeric NULL,
  "실업률" numeric NULL,
  "2년 만기 미국 국채 수익률" numeric NULL,
  "10년 만기 미국 국채 수익률" numeric NULL,
  "금융스트레스지수" numeric NULL,
  "개인 소비 지출" numeric NULL,
  "소비자 물가지수" numeric NULL,
  "5년 변동금리 모기지" numeric NULL,
  "미국 달러 환율" numeric NULL,
  "통화 공급량 M2" numeric NULL,
  "가계 부채 비율" numeric NULL,
  "GDP 성장률" numeric NULL,
  "나스닥 종합지수" numeric NULL,
  "S&P 500 지수" numeric NULL,
  "금 가격" numeric NULL,
  "달러 인덱스" numeric NULL,
  "나스닥 100" numeric NULL,
  "S&P 500 ETF" numeric NULL,
  "QQQ ETF" numeric NULL,
  "러셀 2000 ETF" numeric NULL,
  "다우 존스 ETF" numeric NULL,
  "VIX 지수" numeric NULL,
  "닛케이 225" numeric NULL,
  "상해종합" numeric NULL,
  "항셍" numeric NULL,
  "영국 FTSE" numeric NULL,
  "독일 DAX" numeric NULL,
  "프랑스 CAC 40" numeric NULL,
  "미국 전체 채권시장 ETF" numeric NULL,
  "TIPS ETF" numeric NULL,
  "투자등급 회사채 ETF" numeric NULL,
  "달러/엔" numeric NULL,
  "달러/위안" numeric NULL,
  "미국 리츠 ETF" numeric NULL,
  -- 주가 (시총 탑 50, 나스닥100 기준)
  "엔비디아" numeric NULL,
  "구글 A" numeric NULL,
  "애플" numeric NULL,
  "마이크로소프트" numeric NULL,
  "아마존" numeric NULL,
  "브로드컴" numeric NULL,
  "메타" numeric NULL,
  "테슬라" numeric NULL,
  "월마트" numeric NULL,
  "마이크론" numeric NULL,
  "AMD" numeric NULL,
  "ASML" numeric NULL,
  "인텔" numeric NULL,
  "코스트코" numeric NULL,
  "넷플릭스" numeric NULL,
  "시스코" numeric NULL,
  "팔란티어" numeric NULL,
  "램리서치" numeric NULL,
  "어플라이드 머티리얼즈" numeric NULL,
  "텍사스 인스트루먼트" numeric NULL,
  "린드" numeric NULL,
  "KLA Corp" numeric NULL,
  "Arm" numeric NULL,
  "펩시코" numeric NULL,
  "티모바일" numeric NULL,
  "아나로그디바이스" numeric NULL,
  "샌디스크" numeric NULL,
  "퀄컴" numeric NULL,
  "암젠" numeric NULL,
  "쇼피파이" numeric NULL,
  "씨게이트" numeric NULL,
  "인튜이티브 서지컬" numeric NULL,
  "앱러빈" numeric NULL,
  "팔로알토 네트웍스" numeric NULL,
  "마벨 테크놀로지" numeric NULL,
  "허니웰 인터내셔널" numeric NULL,
  "부킹홀딩스" numeric NULL,
  "스타벅스" numeric NULL,
  "콘스텔레이션 에너지" numeric NULL,
  "인튜이트" numeric NULL,
  "버텍스 파마슈티컬스" numeric NULL,
  "어도비" numeric NULL,
  "컴캐스트" numeric NULL,
  "케이던스" numeric NULL,
  "시놉시스" numeric NULL,
  "메리어트" numeric NULL,
  "메르카도리브레" numeric NULL,
  "ADP" numeric NULL,
  "에어비앤비" numeric NULL,
  "몬델리즈" numeric NULL,
  CONSTRAINT economic_and_stock_data_pkey PRIMARY KEY ("날짜")
) TABLESPACE pg_default;


-- 2. 모델 추론 결과 (wide-format, 날짜별 1행, 종목별 예측/실제값)
create table public.predicted_stocks (
  id serial not null,
  날짜 date not null,
  "엔비디아_Predicted" numeric null,
  "엔비디아_Actual" numeric null,
  "구글 A_Predicted" numeric null,
  "구글 A_Actual" numeric null,
  "애플_Predicted" numeric null,
  "애플_Actual" numeric null,
  "마이크로소프트_Predicted" numeric null,
  "마이크로소프트_Actual" numeric null,
  "아마존_Predicted" numeric null,
  "아마존_Actual" numeric null,
  "브로드컴_Predicted" numeric null,
  "브로드컴_Actual" numeric null,
  "메타_Predicted" numeric null,
  "메타_Actual" numeric null,
  "테슬라_Predicted" numeric null,
  "테슬라_Actual" numeric null,
  "월마트_Predicted" numeric null,
  "월마트_Actual" numeric null,
  "마이크론_Predicted" numeric null,
  "마이크론_Actual" numeric null,
  "AMD_Predicted" numeric null,
  "AMD_Actual" numeric null,
  "ASML_Predicted" numeric null,
  "ASML_Actual" numeric null,
  "인텔_Predicted" numeric null,
  "인텔_Actual" numeric null,
  "코스트코_Predicted" numeric null,
  "코스트코_Actual" numeric null,
  "넷플릭스_Predicted" numeric null,
  "넷플릭스_Actual" numeric null,
  "시스코_Predicted" numeric null,
  "시스코_Actual" numeric null,
  "팔란티어_Predicted" numeric null,
  "팔란티어_Actual" numeric null,
  "램리서치_Predicted" numeric null,
  "램리서치_Actual" numeric null,
  "어플라이드 머티리얼즈_Predicted" numeric null,
  "어플라이드 머티리얼즈_Actual" numeric null,
  "텍사스 인스트루먼트_Predicted" numeric null,
  "텍사스 인스트루먼트_Actual" numeric null,
  "린드_Predicted" numeric null,
  "린드_Actual" numeric null,
  "KLA Corp_Predicted" numeric null,
  "KLA Corp_Actual" numeric null,
  "Arm_Predicted" numeric null,
  "Arm_Actual" numeric null,
  "펩시코_Predicted" numeric null,
  "펩시코_Actual" numeric null,
  "티모바일_Predicted" numeric null,
  "티모바일_Actual" numeric null,
  "아나로그디바이스_Predicted" numeric null,
  "아나로그디바이스_Actual" numeric null,
  "샌디스크_Predicted" numeric null,
  "샌디스크_Actual" numeric null,
  "퀄컴_Predicted" numeric null,
  "퀄컴_Actual" numeric null,
  "암젠_Predicted" numeric null,
  "암젠_Actual" numeric null,
  "쇼피파이_Predicted" numeric null,
  "쇼피파이_Actual" numeric null,
  "씨게이트_Predicted" numeric null,
  "씨게이트_Actual" numeric null,
  "인튜이티브 서지컬_Predicted" numeric null,
  "인튜이티브 서지컬_Actual" numeric null,
  "앱러빈_Predicted" numeric null,
  "앱러빈_Actual" numeric null,
  "팔로알토 네트웍스_Predicted" numeric null,
  "팔로알토 네트웍스_Actual" numeric null,
  "마벨 테크놀로지_Predicted" numeric null,
  "마벨 테크놀로지_Actual" numeric null,
  "허니웰 인터내셔널_Predicted" numeric null,
  "허니웰 인터내셔널_Actual" numeric null,
  "부킹홀딩스_Predicted" numeric null,
  "부킹홀딩스_Actual" numeric null,
  "스타벅스_Predicted" numeric null,
  "스타벅스_Actual" numeric null,
  "콘스텔레이션 에너지_Predicted" numeric null,
  "콘스텔레이션 에너지_Actual" numeric null,
  "인튜이트_Predicted" numeric null,
  "인튜이트_Actual" numeric null,
  "버텍스 파마슈티컬스_Predicted" numeric null,
  "버텍스 파마슈티컬스_Actual" numeric null,
  "어도비_Predicted" numeric null,
  "어도비_Actual" numeric null,
  "컴캐스트_Predicted" numeric null,
  "컴캐스트_Actual" numeric null,
  "케이던스_Predicted" numeric null,
  "케이던스_Actual" numeric null,
  "시놉시스_Predicted" numeric null,
  "시놉시스_Actual" numeric null,
  "메리어트_Predicted" numeric null,
  "메리어트_Actual" numeric null,
  "메르카도리브레_Predicted" numeric null,
  "메르카도리브레_Actual" numeric null,
  "ADP_Predicted" numeric null,
  "ADP_Actual" numeric null,
  "에어비앤비_Predicted" numeric null,
  "에어비앤비_Actual" numeric null,
  "몬델리즈_Predicted" numeric null,
  "몬델리즈_Actual" numeric null,
  created_at timestamp with time zone null default now(),
  constraint predicted_stocks_pkey primary key (id),
  constraint unique_prediction_date unique ("날짜")
) TABLESPACE pg_default;

create index IF not exists idx_predicted_stocks_date on public.predicted_stocks using btree ("날짜") TABLESPACE pg_default;


-- 4. 주식 분석 결과 (row-per-stock, 추론 후 생성)
create table public.stock_analysis_results (
  id serial not null,
  "Stock" text not null,
  "MAE" numeric null,
  "MSE" numeric null,
  "RMSE" numeric null,
  "MAPE (%)" numeric null,
  "Accuracy (%)" numeric null,
  "Last Actual Price" numeric null,
  "Predicted Future Price" numeric null,
  "Predicted Rise" boolean null,
  "Rise Probability (%)" numeric null,
  "Recommendation" text null,
  "Analysis" text null,
  created_at timestamp with time zone null default now(),
  constraint stock_analysis_results_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_stock_analysis_stock on public.stock_analysis_results using btree ("Stock") TABLESPACE pg_default;
create index IF not exists idx_stock_analysis_recommendation on public.stock_analysis_results using btree ("Recommendation") TABLESPACE pg_default;
create index IF not exists idx_stock_analysis_rise_probability on public.stock_analysis_results using btree ("Rise Probability (%)") TABLESPACE pg_default;


-- 5. 기술적 분석 추천 (row-per-stock-per-date)
create table public.stock_recommendations (
  날짜 date not null,
  종목 character varying(50) not null,
  "SMA20" numeric null,
  "SMA50" numeric null,
  골든_크로스 boolean null,
  "RSI" numeric null,
  "MACD" numeric null,
  "Signal" numeric null,
  "MACD_매수_신호" boolean null,
  추천_여부 boolean null,
  constraint stock_recommendations_pkey primary key ("날짜", "종목")
) TABLESPACE pg_default;


-- 6. 감성 분석 결과 (row-per-ticker)
create table public.ticker_sentiment_analysis (
  id serial not null,
  ticker character varying(10) not null,
  average_sentiment_score double precision not null,
  article_count integer not null,
  calculation_date timestamp without time zone not null,
  created_at timestamp without time zone null default CURRENT_TIMESTAMP,
  constraint ticker_sentiment_analysis_pkey primary key (id)
) TABLESPACE pg_default;
