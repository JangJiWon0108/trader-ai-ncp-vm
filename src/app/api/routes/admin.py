"""
관리자(개인용) 운영 도구 API.

프론트 '관리자' 페이지에서 사용:
- 백엔드 상태/스케줄 오버뷰
- 로그 tail 조회
- 텔레그램 샘플 메시지 전송 테스트
- 경제 데이터 수동 갱신/추론 수동 실행
- 현재 모델 디렉터리/추론 완료 여부(오늘 기준)
- KIS API 연결 간단 점검
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytz
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from alarm.telegram import send_telegram_long_text, send_telegram_message_detailed
from app.core.config import settings
from app.db.supabase import supabase
from app.utils.logger import get_logger, root_effective_level_name, tail_memory_logs
from app.utils.scheduler import (
    get_all_schedules_overview,
    run_economic_data_update_now,
    run_inference_now,
    run_manual_buy_now,
    run_manual_sell_now,
    start_economic_data_scheduler,
    start_scheduler,
    start_sell_scheduler,
    stop_economic_data_scheduler,
    stop_scheduler,
    stop_sell_scheduler,
)

logger = get_logger(__name__)
router = APIRouter()


def _kst_today_iso() -> str:
    kst = pytz.timezone("Asia/Seoul")
    return datetime.now(kst).date().isoformat()


def _to_kst_date_iso(dt_like: Any) -> str | None:
    if not dt_like:
        return None
    try:
        dt = datetime.fromisoformat(str(dt_like).replace("Z", "+00:00"))
        kst = pytz.timezone("Asia/Seoul")
        return dt.astimezone(kst).date().isoformat()
    except Exception:
        return None


def _ymd_or_none(s: str | None) -> str | None:
    if s is None:
        return None
    v = (s or "").strip()
    if not v:
        return None
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        return None
    return v


@router.get("/health", summary="운영 상태(설정/스케줄 오버뷰)")
def admin_health():
    try:
        model_path = settings.predict_model_path
        return {
            "ok": True,
            "project": {
                "name": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "debug": bool(settings.DEBUG),
            },
            "kis": {"use_mock": bool(settings.KIS_USE_MOCK), "base_url": settings.kis_base_url},
            "model": {
                "predict_model_dir": str(settings.PREDICT_MODEL_DIR),
                "resolved_path": str(model_path),
                "exists": model_path.exists(),
            },
            "schedules": get_all_schedules_overview(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"health 실패: {str(e)}")


@router.get("/config/public", summary="프론트 표시용 공개 설정(trading/schedule thresholds)")
def admin_public_config():
    """
    프론트에서 표시만 필요한 '런타임 설정값'을 반환한다.
    비밀키/토큰 등 민감정보는 절대 포함하지 않는다.
    """
    try:
        return {
            "project": {
                "name": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "is_mock": bool(settings.KIS_USE_MOCK),
            },
            "schedule": {
                "auto_buy_time_kst": settings.SCHEDULE_AUTO_BUY_TIME,
                "auto_sell_interval_min": int(settings.SCHEDULE_AUTO_SELL_INTERVAL_MIN),
                "economic_update_time_kst": settings.SCHEDULE_ECONOMIC_UPDATE_TIME,
                "startup_run_auto_buy": bool(settings.STARTUP_RUN_AUTO_BUY),
                "after_economic_run_inference": bool(settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE),
                "eod_llm_report_enabled": bool(settings.SCHEDULE_EOD_LLM_REPORT_ENABLED),
                "eod_llm_report_time_kst": settings.SCHEDULE_EOD_LLM_REPORT_TIME_KST,
            },
            "buy": {
                "model_accuracy_min": float(settings.BUY_MODEL_ACCURACY_MIN),
                "rise_prob_min": float(settings.BUY_RISE_PROB_MIN),
                "rsi_max": float(settings.BUY_RSI_MAX),
                "sentiment_min": float(settings.BUY_SENTIMENT_MIN),
                "tech_min_with_sentiment": int(settings.BUY_TECH_MIN_WITH_SENTIMENT),
                "tech_min_without_sentiment": int(settings.BUY_TECH_MIN_WITHOUT_SENTIMENT),
            },
            "sell": {
                "take_profit_pct": float(settings.SELL_TAKE_PROFIT_PCT),
                "stop_loss_pct": float(settings.SELL_STOP_LOSS_PCT),
                "rsi_overbought": float(settings.SELL_RSI_OVERBOUGHT),
                "sentiment_max": float(settings.SELL_SENTIMENT_MAX),
                "tech_min_with_sentiment": int(settings.SELL_TECH_MIN_WITH_SENTIMENT),
                "tech_min_tech_only": int(settings.SELL_TECH_MIN_TECH_ONLY),
                "tech_min_without_sentiment": int(settings.SELL_TECH_MIN_WITHOUT_SENTIMENT),
            },
            "trading": {
                "buy_quantity": int(settings.TRADING_BUY_QUANTITY),
                "buy_amount_usd": float(settings.TRADING_BUY_AMOUNT_USD),
                "max_positions": int(settings.TRADING_MAX_POSITIONS),
                "order_type": settings.TRADING_ORDER_TYPE,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"public config 실패: {str(e)}")


@router.get("/logs", summary="서버 로그 tail")
def admin_logs(
    lines: int = Query(250, ge=10, le=3000, description="반환할 마지막 라인 수"),
    file: str = Query("app.log", description="log 디렉터리 내 파일명 (예: app.log, app.log.1)"),
    source: str = Query("auto", description="로그 소스: auto|file|memory"),
):
    try:
        import os

        repo_root = Path(__file__).resolve().parents[3]
        log_dir = Path(os.getenv("LOG_DIR", str(Path(repo_root) / "log"))).expanduser().resolve()
        target = (log_dir / file).resolve()
        if log_dir not in target.parents:
            raise HTTPException(status_code=400, detail="허용되지 않는 로그 경로입니다.")

        log_to_file = (os.getenv("LOG_TO_FILE", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
        src = (source or "auto").strip().lower()
        if src not in ("auto", "file", "memory"):
            raise HTTPException(status_code=422, detail="source는 auto|file|memory 중 하나여야 합니다.")

        # auto 정책:
        # - LOG_TO_FILE=1 이면 파일 우선(있을 때)
        # - 그 외에는 stdout 기반(memory 링버퍼) 우선
        if src == "auto":
            src = "file" if (log_to_file and target.exists()) else "memory"

        # 1) 파일 tail
        if src == "file":
            if not target.exists():
                raise HTTPException(status_code=404, detail=f"로그 파일이 없습니다: {file}")
            text = target.read_text(encoding="utf-8", errors="replace")
            all_lines = text.splitlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {
                "file": file,
                "lines": len(tail),
                "total_lines": len(all_lines),
                "text": "\n".join(tail),
                "source": "file",
                "log_level": root_effective_level_name(),
            }

        # 2) 메모리 링버퍼 tail (K8s stdout 기본 환경 대응)
        mem_text = tail_memory_logs(lines)
        if mem_text.strip():
            mem_lines = mem_text.splitlines()
            return {
                "file": file,
                "lines": len(mem_lines),
                "total_lines": len(mem_lines),
                "text": mem_text,
                "source": "memory",
                "log_level": root_effective_level_name(),
            }

        # 3) 둘 다 비어 있으면 안내
        if not log_to_file:
            raise HTTPException(status_code=400, detail="현재 프로세스에 쌓인 로그가 없습니다. (쿠버네티스에서는 stdout 로그를 사용하세요)")
        raise HTTPException(status_code=404, detail="로그가 비어 있거나 파일이 없습니다.")

        return {
            "file": file,
            "lines": 0,
            "total_lines": 0,
            "text": "",
            "source": "none",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"logs 실패: {str(e)}")


@router.post("/telegram/test", summary="텔레그램 메시지 샘플 전송")
def admin_telegram_test(payload: dict | None = None):
    try:
        payload = payload or {}
        text = (payload.get("text") or "").strip()
        if not text:
            prefix = (settings.TELEGRAM_MESSAGE_PREFIX or "").strip() or f"[{settings.PROJECT_NAME}]"
            text = f"{prefix} 관리자 테스트 메시지 ({datetime.now().isoformat(timespec='seconds')})"
        # 상세 에러를 프론트에 전달(장애 시 '완료'로 보이는 문제 방지)
        result = send_telegram_message_detailed(text, timeout_sec=20.0)
        return {"sent": bool(result.get("sent")), "text": text, "error": result.get("error")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"telegram test 실패: {str(e)}")


@router.get("/model", summary="현재 사용 중인 모델 디렉터리")
def admin_model_info():
    try:
        p = settings.predict_model_path
        meta = None
        meta_path = p / "model_meta.json"
        if meta_path.exists():
            try:
                import json

                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {"error": "model_meta.json 파싱 실패"}
        return {
            "predict_model_dir": str(settings.PREDICT_MODEL_DIR),
            "resolved_path": str(p),
            "exists": p.exists(),
            "model_meta": meta,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"model info 실패: {str(e)}")


@router.get("/inference/status", summary="오늘(KST) 기준 추론 완료 여부")
def admin_inference_status():
    """
    판단 근거:
    - 추론이 실제로 반영된 '데이터 날짜'는 stock_analysis_results.data_date(max)를 우선 사용한다.
      (없으면 predicted_stocks.날짜(max)로 fallback)
    - expected_data_date_kst = 오늘(KST) - 1일 (경제 지표 저장 종료일과 동일한 가정)
    - latest_data_date == expected_data_date_kst 이면 inferred_today=True 로 간주

    참고:
    - stock_analysis_results.created_at 는 '적재 시각'이라 데이터 날짜와 다를 수 있음(혼란 방지용으로 디버깅 정보만 제공).
    """
    try:
        today = _kst_today_iso()
        kst = pytz.timezone("Asia/Seoul")
        expected = (datetime.now(kst).date()).isoformat()
        # expected는 "오늘"이 아니라 "어제"여야 함
        expected = (datetime.now(kst).date() - timedelta(days=1)).isoformat()

        # 1) 우선: stock_analysis_results.data_date 최신값
        latest_data_date = None
        try:
            a_date = (
                supabase.table("stock_analysis_results")
                .select("data_date")
                .order("data_date", desc=True)
                .limit(1)
                .execute()
            )
            a_date_rows = a_date.data or []
            latest_data_date = (a_date_rows[0] or {}).get("data_date") if a_date_rows else None
        except Exception:
            # 컬럼이 아직 없거나 스키마 캐시 미반영인 경우 fallback
            latest_data_date = None

        # 2) fallback: predicted_stocks.날짜 최신값
        if not latest_data_date:
            pred = (
                supabase.table("predicted_stocks")
                .select("날짜")
                .order("날짜", desc=True)
                .limit(1)
                .execute()
            )
            pred_rows = pred.data or []
            latest_data_date = (pred_rows[0] or {}).get("날짜") if pred_rows else None

        # 디버깅용: 분석 결과 적재 시각도 함께 제공
        a = (
            supabase.table("stock_analysis_results")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        arows = a.data or []
        latest_created_at = (arows[0] or {}).get("created_at") if arows else None

        inferred_today = bool(latest_data_date == expected)
        return {
            "today_kst": today,
            "expected_data_date_kst": expected,
            "latest_data_date": latest_data_date,
            "latest_created_at": str(latest_created_at) if latest_created_at else None,
            # 기존 호환 필드(프론트/기존 코드)
            "latest_kst_date": latest_data_date,
            "inferred_today": inferred_today,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"inference status 실패: {str(e)}")

@router.get("/sentiment/latest", summary="Alpha Vantage 감성 최신 목록(그리드용)")
def admin_sentiment_latest(
    limit: int = Query(120, ge=1, le=500, description="반환할 최대 행 수"),
):
    """
    ticker_sentiment_analysis 테이블의 최신 계산 결과를 반환합니다.

    프론트 그리드 표시 용도(날짜/점수/기사수).
    """
    try:
        resp = (
            supabase.table("ticker_sentiment_analysis")
            .select("ticker,average_sentiment_score,article_count,calculation_date")
            .order("calculation_date", desc=True)
            .limit(limit)
            .execute()
        )
        rows = resp.data or []
        return {"items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sentiment latest 실패: {str(e)}")


@router.get("/sentiment/history", summary="Alpha Vantage 감성 히스토리(날짜 범위/페이지)")
def admin_sentiment_history(
    date_from: str | None = Query(None, description="시작일 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="종료일 YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="1부터 시작"),
    page_size: int = Query(30, ge=1, le=200),
):
    """
    경제 지표 페이지 UX와 동일하게 날짜 범위/페이지로 감성 데이터를 조회합니다.

    ticker_sentiment_analysis.calculation_date 는 문자열(YYYY-MM-DD HH:MM:SS 또는 ISO)일 수 있어
    가장 보수적으로 문자열 범위 검색을 수행합니다.
    """
    df = _ymd_or_none(date_from)
    dt = _ymd_or_none(date_to)
    if date_from and not df:
        raise HTTPException(status_code=422, detail="date_from은 YYYY-MM-DD 형식이어야 합니다.")
    if date_to and not dt:
        raise HTTPException(status_code=422, detail="date_to는 YYYY-MM-DD 형식이어야 합니다.")
    if df and dt and df > dt:
        raise HTTPException(status_code=422, detail="date_from은 date_to보다 늦을 수 없습니다.")

    start_key = f"{df} 00:00:00" if df else None
    end_key = f"{dt} 23:59:59" if dt else None

    try:
        q = supabase.table("ticker_sentiment_analysis").select(
            "ticker,average_sentiment_score,article_count,calculation_date",
            count="exact",
        )
        if start_key:
            q = q.gte("calculation_date", start_key)
        if end_key:
            q = q.lte("calculation_date", end_key)

        offset = (page - 1) * page_size
        resp = (
            q.order("calculation_date", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        items = []
        for r in resp.data or []:
            cd = r.get("calculation_date")
            # 문자열이면 앞 10자(YYYY-MM-DD)로 date를 만들고, 아니면 best-effort
            d = None
            if isinstance(cd, str) and len(cd) >= 10:
                d = cd[:10]
            else:
                d = _to_kst_date_iso(cd)
            items.append(
                {
                    "date": d,
                    "ticker": r.get("ticker"),
                    "average_sentiment_score": r.get("average_sentiment_score"),
                    "article_count": r.get("article_count"),
                    "calculation_date": cd,
                }
            )

        total = resp.count if resp.count is not None else 0
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"sentiment history 실패: {str(e)}")


@router.post("/inference/trigger", summary="경제 갱신 없이 추론만 수동 실행")
def admin_trigger_inference():
    try:
        result = run_inference_now()
        return {"success": True, "result": result}
    except Exception as e:
        logger.exception("수동 추론 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"수동 추론 실패: {str(e)}")


@router.post("/buy/trigger", summary="수동 매수 실행(관리자)")
def admin_trigger_manual_buy():
    """
    관리자 페이지에서 수동 매수를 트리거합니다.

    - 성공/실패 여부와 무관하게 결과를 텔레그램으로 전송합니다.
    - 기존 '자동 매수 결과' 포맷을 유지하고, 제목에 '(수동 매수)' 라벨만 추가합니다.
    """
    try:
        run_manual_buy_now()
        return {"success": True, "message": "수동 매수를 실행했습니다. 텔레그램 결과를 확인하세요."}
    except Exception as e:
        logger.exception("수동 매수 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"수동 매수 실패: {str(e)}")


class ManualSellRequest(BaseModel):
    tickers: list[str]


@router.post("/sell/trigger", summary="수동 매도 실행(관리자)")
def admin_trigger_manual_sell(request: ManualSellRequest):
    """
    지정 티커를 즉시 매도합니다. 전략 룰 무관하게 강제 실행.

    - **tickers**: 매도할 종목 티커 목록 (예: ["AMGN", "ADP"])
    - 결과를 텔레그램으로 전송합니다.
    """
    if not request.tickers:
        raise HTTPException(status_code=400, detail="tickers 목록이 비어있습니다.")
    try:
        result = run_manual_sell_now(request.tickers)
        return {"success": True, "message": "수동 매도를 실행했습니다. 텔레그램 결과를 확인하세요.", "result": result}
    except Exception as e:
        logger.exception("수동 매도 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"수동 매도 실패: {str(e)}")


@router.post("/snapshot/force", summary="총자산 스냅샷 강제 저장")
def admin_force_snapshot():
    from app.services.equity_snapshot_service import save_equity_snapshot_if_due
    try:
        result = save_equity_snapshot_if_due(force=True)
        return {"success": result.get("saved", False), "result": result}
    except Exception as e:
        logger.exception("스냅샷 강제 저장 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"스냅샷 저장 실패: {str(e)}")


@router.get("/inference/history", summary="추론 결과 히스토리(날짜 범위/페이지)")
def admin_inference_history(
    date_from: str | None = Query(None, description="시작일 YYYY-MM-DD (KST 기준)"),
    date_to: str | None = Query(None, description="종료일 YYYY-MM-DD (KST 기준)"),
    page: int = Query(1, ge=1, description="1부터 시작"),
    page_size: int = Query(30, ge=1, le=200),
):
    """
    `stock_analysis_results` 기반. 경제 지표/감성 페이지 UX와 동일하게 날짜 범위/페이지로 조회한다.

    - 필터는 created_at(timestamptz)을 KST 기준 날짜 범위로 변환해 적용한다.
      (Supabase 쿼리에서는 UTC ISO로 변환한 start/end를 gte/lte로 사용)
    """
    df = _ymd_or_none(date_from)
    dt = _ymd_or_none(date_to)
    if date_from and not df:
        raise HTTPException(status_code=422, detail="date_from은 YYYY-MM-DD 형식이어야 합니다.")
    if date_to and not dt:
        raise HTTPException(status_code=422, detail="date_to는 YYYY-MM-DD 형식이어야 합니다.")
    if df and dt and df > dt:
        raise HTTPException(status_code=422, detail="date_from은 date_to보다 늦을 수 없습니다.")

    kst = pytz.timezone("Asia/Seoul")
    start_iso = None
    end_iso = None
    if df:
        start_iso = kst.localize(datetime.fromisoformat(df).replace(hour=0, minute=0, second=0, microsecond=0)).astimezone(pytz.UTC).isoformat()
    if dt:
        end_iso = kst.localize(datetime.fromisoformat(dt).replace(hour=23, minute=59, second=59, microsecond=0)).astimezone(pytz.UTC).isoformat()

    try:
        q = supabase.table("stock_analysis_results").select("*", count="exact")
        if start_iso:
            q = q.gte("created_at", start_iso)
        if end_iso:
            q = q.lte("created_at", end_iso)

        offset = (page - 1) * page_size
        resp = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

        items = []
        for r in resp.data or []:
            created = r.get("created_at")
            items.append(
                {
                    "data_date": r.get("data_date"),
                    "run_date_kst": _to_kst_date_iso(created),
                    "created_at": created,
                    "stock": r.get("Stock"),
                    "accuracy": r.get("Accuracy (%)"),
                    "rise_probability": r.get("Rise Probability (%)"),
                    "recommendation": r.get("Recommendation"),
                    "last_price": r.get("Last Actual Price"),
                    "predicted_price": r.get("Predicted Future Price"),
                }
            )

        total = resp.count if resp.count is not None else 0
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"inference history 실패: {str(e)}")


@router.post("/economic/trigger", summary="경제/주가 데이터 수동 증분 수집(스케줄과 동일)")
def admin_trigger_economic_update():
    try:
        ok = bool(run_economic_data_update_now())
        return {"success": ok}
    except Exception as e:
        logger.exception("수동 경제 업데이트 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"수동 경제 업데이트 실패: {str(e)}")


@router.get("/kis/ping", summary="KIS API 연결 간단 점검")
def admin_kis_ping():
    """
    가장 단순한 '실제 호출 성공 여부' 확인용.
    해외잔고 조회를 통해 토큰/서명/네트워크가 정상인지 확인한다.
    """
    try:
        from app.services.balance_service import get_overseas_balance

        result = get_overseas_balance()
        return {
            "ok": bool(isinstance(result, dict) and result.get("rt_cd") in ("0", "1")),
            "rt_cd": (result or {}).get("rt_cd") if isinstance(result, dict) else None,
            "msg1": (result or {}).get("msg1") if isinstance(result, dict) else None,
            "use_mock": bool(settings.KIS_USE_MOCK),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"kis ping 실패: {str(e)}")


_SCHEDULER_NAMES = frozenset({"economic", "auto_buy", "auto_sell"})
_SCHEDULER_ACTIONS = frozenset({"start", "stop", "restart"})


@router.get("/schedulers/status", summary="백그라운드 스케줄 루프 상태(경제·매수·매도 등)")
def admin_schedulers_status():
    try:
        return {
            "ok": True,
            "schedules": get_all_schedules_overview(),
            "kis_use_mock": bool(settings.KIS_USE_MOCK),
        }
    except Exception as e:
        logger.exception("schedulers/status 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"schedulers/status 실패: {str(e)}")


@router.post(
    "/schedulers/{scheduler_name}/{action}",
    summary="스케줄러 시작·중지·재시작 (economic | auto_buy | auto_sell)",
)
def admin_scheduler_control(scheduler_name: str, action: str):
    name = (scheduler_name or "").strip().lower()
    act = (action or "").strip().lower()
    if name not in _SCHEDULER_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 스케줄러입니다: {scheduler_name!r} (economic|auto_buy|auto_sell)",
        )
    if act not in _SCHEDULER_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 동작입니다: {action!r} (start|stop|restart)",
        )

    steps: list[str] = []

    def _append_stop_start(stop_fn, start_fn, stop_label: str, start_label: str) -> None:
        if act in ("stop", "restart"):
            stopped = bool(stop_fn())
            steps.append(f"{stop_label}: {'완료' if stopped else '이미 중지'}")
        if act in ("start", "restart"):
            started = bool(start_fn())
            steps.append(f"{start_label}: {'완료' if started else '이미 실행 중'}")

    try:
        if name == "economic":
            _append_stop_start(
                stop_economic_data_scheduler,
                start_economic_data_scheduler,
                "경제/주가 스케줄 중지",
                "경제/주가 스케줄 시작",
            )
        elif name == "auto_buy":
            _append_stop_start(
                stop_scheduler,
                start_scheduler,
                "자동 매수 중지",
                "자동 매수 시작",
            )
        elif name == "auto_sell":
            _append_stop_start(
                stop_sell_scheduler,
                start_sell_scheduler,
                "자동 매도 중지",
                "자동 매도 시작",
            )

        return {
            "ok": True,
            "scheduler": name,
            "action": act,
            "message": " · ".join(steps) if steps else act,
            "schedules": get_all_schedules_overview(),
            "kis_use_mock": bool(settings.KIS_USE_MOCK),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("schedulers/%s/%s 실패: %s", name, act, e)
        raise HTTPException(status_code=500, detail=f"스케줄러 제어 실패: {str(e)}")

