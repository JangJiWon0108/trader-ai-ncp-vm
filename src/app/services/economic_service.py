"""
경제·주가 일일 배치: Supabase `economic_and_stock_data` 갱신.

루트 `stock.collect_economic_data` 로 구간 수집 후, 어제까지 행만 DB에 반영한다.
스케줄·앱 기동 시 `update_economic_data_in_background` 가 호출된다.
"""

# ─── 모듈 임포트 ───
from app.utils.logger import get_logger
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.config import settings
from app.db.supabase import supabase
from stock import collect_economic_data

logger = get_logger(__name__)

# ─── 헬퍼 함수 ───


def get_last_updated_date():
    """
    데이터베이스에서 마지막으로 수집된 날짜를 조회합니다.
    """
    try:
        response = (
            supabase.table("economic_and_stock_data")
            .select("날짜")
            .order("날짜", desc=True)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            last_date = datetime.fromisoformat(response.data[0]["날짜"].replace("Z", "+00:00"))
            next_date = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            logger.info(
                "마지막 수집 날짜: %s, 다음 수집 시작일: %s",
                last_date.strftime("%Y-%m-%d"),
                next_date,
            )
            return next_date
        logger.info("기존 데이터 없음 — 기본 시작 날짜(2006-01-01)")
        return "2006-01-01"
    except Exception as e:
        logger.warning("마지막 수집 날짜 조회 오류: %s", e, exc_info=True)
        return "2006-01-01"


def get_existing_data_with_nulls():
    """
    NULL 값이 있는 기존 데이터를 조회합니다.
    """
    try:
        query = "SELECT * FROM economic_and_stock_data WHERE jsonb_object_keys(data::jsonb) @> '{null}'::jsonb"
        response = supabase.table("economic_and_stock_data").select("*").execute(query)

        if response.data and len(response.data) > 0:
            df = pd.DataFrame(response.data)
            logger.info("NULL 값이 포함된 레코드 %s개 발견", len(df))
            return df
        logger.info("NULL 값이 포함된 레코드 없음")
        return pd.DataFrame()
    except Exception as e:
        logger.warning("NULL 값 데이터 조회 오류: %s", e, exc_info=True)
        return pd.DataFrame()


# ─── 상수 정의 ───

stock_columns = [
    "나스닥 종합지수",
    "S&P 500 지수",
    "금 가격",
    "달러 인덱스",
    "나스닥 100",
    "S&P 500 ETF",
    "QQQ ETF",
    "러셀 2000 ETF",
    "다우 존스 ETF",
    "VIX 지수",
    "닛케이 225",
    "상해종합",
    "항셍",
    "영국 FTSE",
    "독일 DAX",
    "프랑스 CAC 40",
    "미국 전체 채권시장 ETF",
    "TIPS ETF",
    "투자등급 회사채 ETF",
    "달러/엔",
    "달러/위안",
    "미국 리츠 ETF",
    "엔비디아",
    "구글 A",
    "애플",
    "마이크로소프트",
    "아마존",
    "브로드컴",
    "메타",
    "테슬라",
    "월마트",
    "마이크론",
    "AMD",
    "ASML",
    "인텔",
    "코스트코",
    "넷플릭스",
    "시스코",
    "팔란티어",
    "램리서치",
    "어플라이드 머티리얼즈",
    "텍사스 인스트루먼트",
    "린드",
    "KLA Corp",
    "Arm",
    "펩시코",
    "티모바일",
    "아나로그디바이스",
    "샌디스크",
    "퀄컴",
    "암젠",
    "쇼피파이",
    "씨게이트",
    "인튜이티브 서지컬",
    "앱러빈",
    "팔로알토 네트웍스",
    "마벨 테크놀로지",
    "부킹홀딩스",
    "스타벅스",
    "콘스텔레이션 에너지",
    "인튜이트",
    "버텍스 파마슈티컬스",
    "어도비",
    "컴캐스트",
    "케이던스",
    "시놉시스",
    "메리어트",
    "메르카도리브레",
    "ADP",
    "에어비앤비",
    "몬델리즈",
]

economic_columns = [
    "10년 기대 인플레이션율",
    "장단기 금리차",
    "기준금리",
    "미시간대 소비자 심리지수",
    "실업률",
    "2년 만기 미국 국채 수익률",
    "10년 만기 미국 국채 수익률",
    "금융스트레스지수",
    "개인 소비 지출",
    "소비자 물가지수",
    "5년 변동금리 모기지",
    "미국 달러 환율",
    "통화 공급량 M2",
    "가계 부채 비율",
    "GDP 성장률",
]

# ─── 공개 API ───


async def update_economic_data_in_background():
    """
    백그라운드에서 경제 지표 데이터를 업데이트
    """
    try:
        logger.info("경제 지표 및 주가 데이터 업데이트 작업 시작")

        start_date = get_last_updated_date()

        # 저장 종료일은 KST '어제'로 고정 (서버/컨테이너 타임존(UTC) 차이로 날짜가 흔들리는 문제 방지)
        import pytz

        kst = pytz.timezone("Asia/Seoul")
        now_kst = datetime.now(kst)
        today = now_kst.strftime("%Y-%m-%d")
        yesterday = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")
        # wide 테이블(economic_and_stock_data) 행 단위 적재 시각
        synced_at = datetime.now(timezone.utc).isoformat()

        collection_end_date = today
        storage_end_date = yesterday

        if start_date > storage_end_date:
            logger.info(
                "수집 시작일(%s)이 저장 종료일(%s)보다 큼 — 수집할 데이터 없음",
                start_date,
                storage_end_date,
            )
            return {
                "success": True,
                "message": "수집할 데이터 없음 (시작일이 저장 종료일보다 큼)",
                "total_records": 0,
                "updated_records": 0,
                "date_range": {
                    "start_date": start_date,
                    "storage_end_date": storage_end_date,
                    "collection_end_date": collection_end_date,
                },
            }

        previous_date = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        prev_data_response = supabase.table("economic_and_stock_data").select("*").eq("날짜", previous_date).execute()
        previous_data = prev_data_response.data[0] if prev_data_response.data else {}

        new_data = collect_economic_data(start_date=start_date, end_date=collection_end_date)

        logger.info("=== 수집된 데이터 확인 ===")
        for date_idx in new_data.index:
            date_str = date_idx.strftime("%Y-%m-%d") if isinstance(date_idx, pd.Timestamp) else date_idx
            logger.info("날짜: %s", date_str)
            for stock in stock_columns[:5]:
                if stock in new_data.columns:
                    logger.info("  %s: %s", stock, new_data.loc[date_idx, stock])

        if new_data is None or new_data.empty:
            logger.info("수집할 새 데이터 없음")
            return {
                "success": True,
                "message": "수집할 새 데이터가 없음",
                "total_records": 0,
                "updated_records": 0,
                "date_range": {
                    "start_date": start_date,
                    "storage_end_date": storage_end_date,
                    "collection_end_date": collection_end_date,
                },
            }

        all_dates = pd.date_range(start=start_date, end=storage_end_date)

        # 메모리에서 forward-fill 후 bulk upsert (날짜당 HTTP 1회 → 배치당 1회)
        rows_to_upsert = []
        for date in all_dates:
            date_str = date.strftime("%Y-%m-%d")
            data_dict: dict = {}

            if date in new_data.index:
                row = new_data.loc[date]
                for col_name, value in row.items():
                    if not pd.isna(value):
                        # numpy 타입 → Python 기본 타입 변환
                        data_dict[col_name] = float(value) if hasattr(value, "item") else value

            for col_name, value in previous_data.items():
                if col_name != "날짜" and col_name not in data_dict and value is not None:
                    data_dict[col_name] = value

            upsert_row: dict = {"날짜": date_str}
            upsert_row.update(data_dict)
            upsert_row["synced_at"] = synced_at
            rows_to_upsert.append(upsert_row)

            if data_dict:
                previous_data = {"날짜": date_str, **data_dict}

        # 배치 upsert (500행씩)
        BATCH_SIZE = 500
        total_records = len(rows_to_upsert)
        for i in range(0, total_records, BATCH_SIZE):
            batch = rows_to_upsert[i : i + BATCH_SIZE]
            supabase.table("economic_and_stock_data").upsert(batch, on_conflict="날짜").execute()
            logger.info("upsert %s/%s 완료", min(i + BATCH_SIZE, total_records), total_records)

        saved_count = total_records
        logger.info("총 %s개 날짜 bulk upsert 완료", total_records)

        return {
            "success": True,
            "message": "경제 데이터 업데이트 완료",
            "total_records": total_records,
            "updated_records": saved_count,
            "date_range": {
                "start_date": start_date,
                "storage_end_date": storage_end_date,
                "collection_end_date": collection_end_date,
            },
        }
    except Exception as e:
        logger.exception("경제 데이터 업데이트 실패: %s", e)
        tb = traceback.format_exc()
        return {"success": False, "error": str(e), "traceback": tb}


logger.info("economic_service 로드 — Supabase URL: %s", settings.SUPABASE_URL)
