"""일일/단건 로그 → Supabase (daily_buy_logs, daily_economic_logs, daily_inference_logs, daily_eod_llm_logs, order_history)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz

from app.utils.logger import get_logger

log = get_logger(__name__)


def _now_kst_iso() -> str:
    return datetime.now(pytz.timezone("Asia/Seoul")).isoformat()


def _ny_date() -> str:
    return datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")


def _db():
    from app.db.supabase import supabase
    return supabase


# ── 매수 ──────────────────────────────────────────────────────────────────────

def save_daily_buy_log(summary: dict) -> int | None:
    summary = summary or {}
    row: dict[str, Any] = {
        "kst_at": _now_kst_iso(),
        "ny_trading_date": summary.get("ny_trading_date") or _ny_date(),
        "success": summary.get("success"),
        "status": str(summary.get("status") or "unknown"),
        "candidate_count": summary.get("candidate_count"),
        "ordered_count": summary.get("ordered_count"),
        "payload": summary,
        "telegram_sent": summary.get("telegram_sent"),
    }
    try:
        ins = _db().table("daily_buy_logs").insert(row).execute()
        rows = ins.data or []
        if not rows:
            return None
        run_id = int(rows[0]["id"])

        items = summary.get("items") or []
        if items:
            bulk = [
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
                }
                for it in items if isinstance(it, dict)
            ]
            if bulk:
                try:
                    _db().table("daily_buy_items").insert(bulk).execute()
                except Exception as e:
                    log.warning("daily_buy_items 저장 실패: %s", e)
        return run_id
    except Exception as e:
        log.warning("daily_buy_logs 저장 실패: %s", e, exc_info=True)
        return None


# ── 경제 데이터 ───────────────────────────────────────────────────────────────

def save_daily_economic_log(result: dict, telegram_sent: bool = False) -> None:
    result = result or {}
    row: dict[str, Any] = {
        "kst_at": _now_kst_iso(),
        "ny_trading_date": _ny_date(),
        "success": result.get("success"),
        "status": "success" if result.get("success") else "failed",
        "updated_records": result.get("updated_records"),
        "error": result.get("error"),
        "payload": result,
        "telegram_sent": telegram_sent,
    }
    try:
        _db().table("daily_economic_logs").insert(row).execute()
    except Exception as e:
        log.warning("daily_economic_logs 저장 실패: %s", e, exc_info=True)


# ── 추론 ──────────────────────────────────────────────────────────────────────

def save_daily_inference_log(result: dict, telegram_sent: bool = False) -> None:
    result = result or {}
    success = not result.get("error") and result.get("prediction_rows") is not None
    row: dict[str, Any] = {
        "kst_at": _now_kst_iso(),
        "ny_trading_date": _ny_date(),
        "success": success,
        "status": "success" if success else "failed",
        "error": result.get("error"),
        "payload": result,
        "telegram_sent": telegram_sent,
    }
    try:
        _db().table("daily_inference_logs").insert(row).execute()
    except Exception as e:
        log.warning("daily_inference_logs 저장 실패: %s", e, exc_info=True)


# ── EOD LLM ───────────────────────────────────────────────────────────────────

def save_daily_eod_llm_log(
    ny_date: str,
    status: str,
    report_text: str | None = None,
    error: str | None = None,
    phase: str | None = None,
    telegram_sent: bool = False,
) -> None:
    row: dict[str, Any] = {
        "kst_at": _now_kst_iso(),
        "ny_trading_date": ny_date,
        "success": status == "sent",
        "status": status,
        "report_text": report_text,
        "error": str(error) if error else None,
        "phase": phase,
        "telegram_sent": telegram_sent,
    }
    try:
        _db().table("daily_eod_llm_logs").insert(row).execute()
    except Exception as e:
        log.warning("daily_eod_llm_logs 저장 실패: %s", e, exc_info=True)


# ── 주문 단건 이력 ─────────────────────────────────────────────────────────────

def _compute_portfolio_snapshot() -> tuple[float | None, float | None]:
    """DB 스냅샷 기준 (holdings_return_pct, seed_return_pct). 오류 시 (None, None)."""
    try:
        db = _db()
        h_resp = db.table("holdings").select("raw").execute()
        s_resp = db.table("holdings_summary").select("cash_usd, initial_cash_usd").eq("id", "main").execute()
        holdings = [r["raw"] for r in (h_resp.data or []) if r.get("raw")]
        summary = (s_resp.data or [{}])[0]
        cash_usd = float(summary.get("cash_usd") or 0)
        seed_raw = summary.get("initial_cash_usd")
        seed_usd = float(seed_raw) if seed_raw is not None else None

        total_cost = 0.0
        total_eval = 0.0
        for h in holdings:
            qty = float(h.get("ovrs_cblc_qty") or 0)
            buy_amt = float(h.get("frcr_buy_amt_smtl1") or 0)
            if buy_amt <= 0:
                buy_amt = qty * float(h.get("pchs_avg_pric") or 0)
            eval_amt = qty * float(h.get("now_pric2") or 0)
            total_cost += buy_amt
            total_eval += eval_amt

        holdings_return_pct = round((total_eval - total_cost) / total_cost * 100, 4) if total_cost > 0 else None
        total_assets = total_eval + cash_usd
        seed_return_pct = round((total_assets - seed_usd) / seed_usd * 100, 4) if seed_usd and seed_usd > 0 else None
        return holdings_return_pct, seed_return_pct
    except Exception:
        return None, None


def save_order(
    *,
    side: str,
    ticker: str,
    stock_name: str | None = None,
    exchange_code: str | None = None,
    quantity: int | None = None,
    limit_price: float | None = None,
    order_type: str | None = None,
    rt_cd: str | None = None,
    api_message: str | None = None,
    success: bool | None = None,
    source: str | None = None,
    payload: dict | None = None,
    ny_trading_date: str | None = None,
) -> None:
    holdings_return_pct, seed_return_pct = _compute_portfolio_snapshot()
    row: dict[str, Any] = {
        "kst_at": _now_kst_iso(),
        "ny_trading_date": ny_trading_date or _ny_date(),
        "side": side,
        "ticker": ticker,
        "stock_name": stock_name,
        "exchange_code": exchange_code,
        "quantity": quantity,
        "limit_price": limit_price,
        "order_type": order_type,
        "rt_cd": rt_cd,
        "api_message": api_message,
        "success": success,
        "source": source,
        "payload": payload,
        "snapshot_holdings_return_pct": holdings_return_pct,
        "snapshot_seed_return_pct": seed_return_pct,
    }
    try:
        _db().table("order_history").insert(row).execute()
    except Exception as e:
        log.warning("order_history 저장 실패: %s", e, exc_info=True)
