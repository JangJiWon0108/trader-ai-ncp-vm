-- ============================================================
-- 추가 DDL (프론트 표시용: KIS 스냅샷 → Supabase)
-- ============================================================
--
-- 목표:
-- - 프론트(대시보드/주문 화면 등)는 KIS를 직접 호출하지 않고, 항상 Supabase 값을 읽는다.
-- - 장중에는 스케줄러가 KIS → Supabase로 주기 동기화하여 최신값을 유지한다.
-- - 장외에도 마지막 스냅샷이 남아 "값이 비는 문제"를 피한다.
--
-- 주의:
-- - 이 파일은 `app/db/ddl.md`에 없는 "추가 테이블"만 정의한다.
-- - raw 컬럼(JSONB)에 KIS 원본 응답을 그대로 저장하고, API는 이를 그대로 반환한다.

-- 1) 해외주식 잔고(보유 종목) 스냅샷
create table if not exists public.holdings (
  ticker text primary key,
  name text,
  qty text,
  avg_price text,
  current_price text,
  pnl_amount text,
  pnl_rate text,
  buy_amount text,
  raw jsonb not null,
  synced_at timestamptz not null default now()
);

-- 1-1) 잔고 요약(예수금 추정치 등)
create table if not exists public.holdings_summary (
  id text primary key, -- "main"
  cash_usd numeric,
  output2 jsonb,
  synced_at timestamptz not null default now()
);

-- 2) 해외주식 체결 내역 스냅샷
create table if not exists public.order_fills (
  fill_key text primary key,
  odno text,
  ord_dt text,
  ord_tmd text,
  ticker text,
  name text,
  side_cd text,
  side_name text,
  qty text,
  price text,
  amount text,
  exchange text,
  status text,
  raw jsonb not null,
  synced_at timestamptz not null default now()
);

create index if not exists idx_order_fills_ord_dt on public.order_fills using btree (ord_dt);

-- 3) 해외주식 미체결(주문잔량) 스냅샷
create table if not exists public.open_orders (
  open_key text primary key,
  odno text,
  ord_dt text,
  ticker text,
  exchange text,
  raw jsonb not null,
  synced_at timestamptz not null default now()
);

create index if not exists idx_open_orders_ord_dt on public.open_orders using btree (ord_dt);

-- ============================================================
-- 추가 ALTER (기존 테이블 컬럼 보강: 날짜 컬럼 정합성)
-- ============================================================

-- A) AI 추론 결과: 데이터 기준일(경제/주가 데이터 날짜) 저장용
-- - 프론트 그리드는 created_at(적재시각)이 아니라 data_date(기준일)를 표시해야 혼란이 없다.
alter table public.stock_analysis_results
add column if not exists data_date date null;

create index if not exists idx_stock_analysis_results_data_date
on public.stock_analysis_results using btree (data_date);

-- B) 감성 결과: 날짜 범위 질의가 잦다면 '기준일(date)' 컬럼을 별도로 두는 것을 권장
-- - 현재는 calculation_date(timestamp)만 있어, 일 단위 집계/필터에 불편할 수 있다.
-- - 주의: calculation_date가 timezone 정보가 없는 timestamp라, "KST 기준 날짜"가 필요하면
--         서비스 레이어에서 date_kst를 명시적으로 저장하는 쪽이 안전하다.
alter table public.ticker_sentiment_analysis
add column if not exists date_kst date null;

create index if not exists idx_ticker_sentiment_analysis_date_kst
on public.ticker_sentiment_analysis using btree (date_kst);

-- (권장) 일별 누적 저장을 위한 유니크 키: (date_kst, ticker)
-- - 오늘 이미 적재되어 있으면 스킵 / 강제 갱신 시 오늘치만 재적재 / 누적 히스토리 유지
create unique index if not exists uq_ticker_sentiment_analysis_date_ticker
on public.ticker_sentiment_analysis (date_kst, ticker);

-- C) 기술적 분석 추천: 기준일(날짜)은 있지만 "적재 시각"이 없으면 운영 점검/디버깅이 어렵다.
-- - 매번 전체 삭제 후 재적재를 하므로, 최신 적재 시각을 남겨두는 용도.
alter table public.stock_recommendations
add column if not exists created_at timestamptz not null default now();

create index if not exists idx_stock_recommendations_created_at
on public.stock_recommendations using btree (created_at);

-- E) equity_snapshots: 시드 기준 수익률 컬럼 추가
alter table public.equity_snapshots
add column if not exists seed_return_pct numeric null;

-- D) 경제/주가 원천 데이터(wide 테이블): 기준일(날짜)과 별개로 "이 행이 DB에 언제 적재/갱신됐는지" 기록
-- - 운영/디버깅 시 "데이터가 최신 적재 되었나?"를 테이블 자체에서 바로 확인 가능
alter table public.economic_and_stock_data
add column if not exists synced_at timestamptz not null default now();

create index if not exists idx_economic_and_stock_data_synced_at
on public.economic_and_stock_data using btree (synced_at);
