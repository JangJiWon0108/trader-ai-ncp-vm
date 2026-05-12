"""
경제·주가 데이터 API.

Supabase `economic_and_stock_data` 조회, 백그라운드 갱신 트리거를 제공한다.
"""

# ─── 모듈 임포트 ───
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.schemas.stock import UpdateResponse
from app.utils.scheduler import run_economic_data_update_now
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ─── 헬퍼 함수 ───


def _parse_iso_date(label: str, value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    s = value.strip()
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{label}는 YYYY-MM-DD 형식이어야 합니다: {value}")
    return s


# ─── 엔드포인트 핸들러 ───


@router.get("/history", summary="날짜별 경제·주식 데이터 (페이지)")
def get_economic_history(
    date_from: str | None = Query(None, description="시작일 YYYY-MM-DD (미입력 시 제한 없음)"),
    date_to: str | None = Query(None, description="종료일 YYYY-MM-DD (미입력 시 제한 없음)"),
    page: int = Query(1, ge=1, description="1부터 시작"),
    page_size: int = Query(15, ge=1, le=100),
):
    """economic_and_stock_data 테이블을 날짜 기준 내림차순으로 페이지 조회합니다."""
    from app.db.supabase import supabase

    df = _parse_iso_date("date_from", date_from)
    dt = _parse_iso_date("date_to", date_to)
    if df and dt and df > dt:
        raise HTTPException(status_code=422, detail="date_from은 date_to보다 늦을 수 없습니다.")

    try:
        q = supabase.table("economic_and_stock_data").select("*", count="exact")
        if df:
            q = q.gte("날짜", df)
        if dt:
            q = q.lte("날짜", dt)
        offset = (page - 1) * page_size
        resp = q.order("날짜", desc=True).range(offset, offset + page_size - 1).execute()
        total = resp.count if resp.count is not None else 0
        items: list[dict[str, Any]] = []
        for row in resp.data or []:
            r = dict(row)
            d = r.pop("날짜", None)
            items.append({"date": d, "data": r})
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest", summary="최신 경제 지표 조회")
def get_latest_economic_data():
    """Supabase economic_and_stock_data 테이블에서 최신 행 반환"""
    from app.db.supabase import supabase

    try:
        resp = (
            supabase.table("economic_and_stock_data")
            .select("*")
            .order("날짜", desc=True)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return {"date": None, "data": {}}
        row = resp.data[0]
        date = row.pop("날짜", None)
        return {"date": date, "data": row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update", summary="경제 및 주식 데이터 업데이트", response_model=UpdateResponse)
async def update_economic_data(
    background_tasks: BackgroundTasks,
):
    """
    경제 및 주식 데이터를 Supabase에 저장합니다.
    이 작업은 백그라운드에서 실행되어 API 응답을 블로킹하지 않습니다.

    DB에서 마지막 수집 날짜를 자동으로 찾아 그 다음 날부터 수집합니다.
    기존 데이터의 NULL 값은 새 데이터로 자동 업데이트됩니다.
    """
    try:
        background_tasks.add_task(run_economic_data_update_now)

        return {
            "success": True,
            "message": "경제 데이터 업데이트가 백그라운드에서 시작되었습니다.",
            "total_records": 0,
            "updated_records": 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 업데이트 중 오류 발생: {str(e)}")


