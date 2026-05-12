"""스케줄러 분 단위 실행 결과 → Supabase `scheduler_minute_logs` (+ 선택 `scheduler_minute_items`)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz

from app.utils.logger import get_logger

log = get_logger(__name__)


def save_scheduler_minute_log(job_type: str, summary: dict) -> int | None:
    """
    summary: `_execute_auto_sell` 등이 반환하는 dict 전체를 payload 로 저장.
    items 가 있으면 scheduler_minute_items 에 행 단위로도 적재(테이블이 있을 때).
    """
    summary = summary or {}
    kst = datetime.now(pytz.timezone("Asia/Seoul"))
    ny = datetime.now(pytz.timezone("America/New_York"))
    ny_date = (summary.get("ny_trading_date") or "").strip() or ny.strftime("%Y-%m-%d")

    head: dict[str, Any] = {
        "job_type": job_type,
        "kst_at": kst.isoformat(),
        "ny_et_at": ny.isoformat(),
        "ny_trading_date": ny_date,
        "market_hours": summary.get("market_hours"),
        "status": str(summary.get("status") or "unknown"),
        "success": summary.get("success"),
        "candidate_count": summary.get("candidate_count"),
        "payload": summary,
        "telegram_sent": summary.get("telegram_sent"),
    }

    try:
        from app.db.supabase import supabase

        ins = supabase.table("scheduler_minute_logs").insert(head).execute()
        rows = ins.data or []
        if not rows:
            log.warning("scheduler_minute_logs insert 응답에 id 없음")
            return None
        run_id = int(rows[0]["id"])

        items = summary.get("items") or []
        if items:
            try:
                bulk: list[dict[str, Any]] = []
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    bulk.append(
                        {
                            "run_id": run_id,
                            "ticker": it.get("ticker"),
                            "stock_name": it.get("stock_name"),
                            "outcome": str(it.get("outcome") or "unknown"),
                            "exchange_code": it.get("exchange_code"),
                            "quantity": it.get("quantity"),
                            "limit_price": it.get("limit_price"),
                            "error": it.get("error"),
                            "api_message": it.get("api_message"),
                            "sell_reasons": it.get("sell_reasons"),
                        }
                    )
                if bulk:
                    supabase.table("scheduler_minute_items").insert(bulk).execute()
            except Exception as ie:
                log.warning(
                    "scheduler_minute_items 적재 실패(부모 로그는 저장됨): %s", ie,
                    exc_info=True,
                )

        return run_id
    except Exception as e:
        log.warning(
            "scheduler_minute_logs 저장 실패(테이블 미생성·RLS·네트워크 등): %s",
            e,
            exc_info=True,
        )
        return None
