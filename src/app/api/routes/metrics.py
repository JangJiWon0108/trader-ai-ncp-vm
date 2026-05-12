"""
대시보드 메트릭(시계열) API.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.equity_snapshot_service import list_equity_snapshots

router = APIRouter()


@router.get("/equity", summary="총자산/총수익률 스냅샷(시계열) 조회")
def read_equity_snapshots(
    days: int = Query(7, ge=1, le=90, description="조회 기간(일). 정규장 1시간 스냅샷 기준(ET 10:00~16:00)"),
):
    items = list_equity_snapshots(days=days)
    return {"ok": True, "days": days, "count": len(items), "items": items}

