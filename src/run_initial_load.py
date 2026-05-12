"""
Supabase 초기 데이터 적재 스크립트
- FRED + Yahoo Finance에서 2006-01-01 ~ 오늘까지 데이터 수집
- Supabase economic_and_stock_data 테이블에 bulk upsert
"""
import sys
import math
import pandas as pd
from datetime import datetime, timedelta, timezone

sys.path.insert(0, '.')

from stock import collect_economic_data
from supabase import create_client

SUPABASE_URL = "https://cubyfztyjnyqbsiemhay.supabase.co"
SUPABASE_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN1YnlmenR5am55cWJzaWVtaGF5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzgwMTgxMiwiZXhwIjoyMDkzMzc3ODEyfQ.1I1StMUdPfRVsHDNaKPAUcR70AJVJ-_25pdjPS_O4J8"
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

START_DATE = "2006-01-01"
END_DATE   = (datetime.today() - timedelta(days=1)).strftime('%Y-%m-%d')  # 어제까지
CHUNK_SIZE = 500


def clean_record(record: dict) -> dict:
    """NaN/inf → None, float → Python float 변환"""
    cleaned = {}
    for k, v in record.items():
        if v is None:
            cleaned[k] = None
        elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            cleaned[k] = None
        elif hasattr(v, 'item'):  # numpy scalar
            cleaned[k] = v.item() if not math.isnan(v.item()) else None
        else:
            cleaned[k] = v
    return cleaned


def upsert_chunk(records: list):
    supabase.table("economic_and_stock_data").upsert(
        records, on_conflict="날짜"
    ).execute()


def main():
    print(f"=== 데이터 수집 시작: {START_DATE} ~ {END_DATE} ===\n")

    # 1. API에서 데이터 수집
    df = collect_economic_data(start_date=START_DATE, end_date=END_DATE)

    if df is None or df.empty:
        print("수집된 데이터가 없습니다.")
        return

    print(f"\n수집 완료: {len(df)}행 × {len(df.columns)}열")

    # 2. 날짜 인덱스 → 컬럼으로, YYYY-MM-DD 문자열
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df.index = df.index.strftime('%Y-%m-%d')
    df.index.name = '날짜'
    df = df.reset_index()

    # 3. NaN 처리 후 레코드 변환
    synced_at = datetime.now(timezone.utc).isoformat()
    records = []
    for _, row in df.iterrows():
        rec = clean_record(row.to_dict())
        rec["synced_at"] = synced_at
        records.append(rec)

    print(f"총 {len(records)}개 레코드 Supabase upsert 시작...\n")

    # 4. 청크 단위 upsert
    total_chunks = (len(records) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(0, len(records), CHUNK_SIZE):
        chunk = records[i:i + CHUNK_SIZE]
        chunk_num = i // CHUNK_SIZE + 1
        try:
            upsert_chunk(chunk)
            print(f"  [{chunk_num}/{total_chunks}] {chunk[0]['날짜']} ~ {chunk[-1]['날짜']} 저장 완료 ({len(chunk)}행)")
        except Exception as e:
            print(f"  [{chunk_num}/{total_chunks}] 오류 발생: {e}")
            # 실패한 청크를 1건씩 재시도
            print("  → 1건씩 재시도 중...")
            for rec in chunk:
                try:
                    supabase.table("economic_and_stock_data").upsert(rec, on_conflict="날짜").execute()
                except Exception as e2:
                    print(f"    {rec.get('날짜')} 저장 실패: {e2}")

    # 5. 결과 확인
    resp = supabase.table("economic_and_stock_data").select("날짜", count="exact").execute()
    print(f"\n=== 완료 === DB 총 행 수: {resp.count}")


if __name__ == "__main__":
    main()
