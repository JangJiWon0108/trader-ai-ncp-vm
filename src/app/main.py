"""
FastAPI 애플리케이션 진입점.

CORS·API 라우터 등록, lifespan 에서 경제 데이터 1회 갱신·텔레그램 알림·
매수·매도·경제 지표 스케줄러를 기동한다. 종료 시 스케줄러만 정리한다.
"""

# ─── 모듈 임포트 ───
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
import uuid

# `uv run python app/main.py` 처럼 파일을 직접 실행할 때도
# `from app...` 임포트가 되도록 프로젝트 루트를 sys.path 에 추가한다.
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.logger import get_logger, harmonize_uvicorn_fastapi_loggers
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from alarm.notify import notify_telegram_economic_update, notify_telegram_inference_skipped
from app.api.api import api_router
from app.core.config import settings
from app.services.economic_service import update_economic_data_in_background
from app.services.stock_recommendation_service import StockRecommendationService
from app.utils.scheduler import (
    get_all_schedules_overview,
  run_auto_buy_now,
  run_inference_now,
    start_economic_data_scheduler,
    start_scheduler,
    start_sell_scheduler,
    stop_economic_data_scheduler,
    stop_scheduler,
    stop_sell_scheduler,
)

logger = get_logger(__name__)

# ─── lifespan ───




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: 앱 기동 시 1회
    await startup()
    yield
    # Shutdown: 스케줄러 정리
    stop_scheduler()
    stop_sell_scheduler()
    stop_economic_data_scheduler()


# ─── 앱 인스턴스 ───

app = FastAPI(title="주식 분석 및 추천 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


class _RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = (request.headers.get("x-request-id") or "").strip() or uuid.uuid4().hex
        request.state.request_id = rid
        response: Response = await call_next(request)
        try:
            response.headers["x-request-id"] = rid
        except Exception:
            pass
        return response


app.add_middleware(_RequestIdMiddleware)


def _req_id(request: Request) -> str:
    try:
        rid = getattr(request.state, "request_id", None)
        if isinstance(rid, str) and rid.strip():
            return rid.strip()
    except Exception:
        pass
    return uuid.uuid4().hex


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = _req_id(request)
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": rid},
        headers={"x-request-id": rid},
    )


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    """
    HTTPException 응답에도 request_id/x-request-id를 통일적으로 포함한다.
    (기본 FastAPI 핸들러는 request_id를 모르므로, 운영/프론트 장애 추적이 어려움)
    """
    rid = _req_id(request)
    return JSONResponse(
        status_code=int(exc.status_code),
        content={"detail": exc.detail, "request_id": rid},
        headers={"x-request-id": rid},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """
    최후의 안전망.

    - 프론트는 `detail`/`message`를 파싱하므로, 반드시 `detail`을 포함한다.
    - 기존 성공 응답/라우터 로직은 변경하지 않는다.
    """
    rid = _req_id(request)
    logger.exception("Unhandled exception (request_id=%s, path=%s): %s", rid, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"서버 내부 오류가 발생했습니다. (request_id={rid})",
            "request_id": rid,
        },
        headers={"x-request-id": rid},
    )


@app.get("/")
def read_root():
    return {"message": "주식 분석 및 추천 API에 오신 것을 환영합니다"}


@app.get("/healthz")
def healthz():
    """Kubernetes liveness/readiness 용 — DB·외부 API 없이 가볍게."""
    return {"status": "ok"}


# ─── 기동 로직 ───


async def startup():
    """서비스 기동 시 경제 데이터 1회 수집 후(필요 시 추론) 스케줄러 시작.

    추가 동작:
    - 서버 기동 직후 1회: 경제/주가 데이터 수집 → (신규 행 있으면) 추론 → 자동 매수 1회 실행
    """
    # uvicorn 기본 logging dictConfig 이후에도 access/error가 루트·링버퍼로 오도록 재맞춤
    harmonize_uvicorn_fastapi_loggers()
    logger.info("서비스 시작 시 경제 데이터 수집 즉시 실행")
    try:
        result = await update_economic_data_in_background()
    except Exception as e:
        result = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        logger.exception("초기 경제 데이터 수집 예외: %s", e)

    notify_payload = result if isinstance(result, dict) else {}
    notify_telegram_economic_update(notify_payload, source="서버시작")

    if isinstance(result, dict) and result.get("success"):
        logger.info("초기 경제 데이터 수집 완료")
    else:
        logger.warning("초기 경제 데이터 수집 실패 또는 스킵: %s", result)

    # 서버 시작 시 1회: (신규 저장 행이 있으면) 추론 → 자동 매수 1회
    try:
        updated = int((result or {}).get("updated_records") or 0) if isinstance(result, dict) else 0
        if settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE and updated > 0:
            logger.info("서버 시작: 신규 저장 행 %s건 → 추론 1회 실행", updated)
            await asyncio.to_thread(run_inference_now)
        else:
            logger.info(
                "서버 시작: 추론 스킵 (after_inference=%s, updated_records=%s)",
                bool(settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE),
                updated,
            )
            # 스케줄 경로와 동일하게, 스킵이어도 결과를 텔레그램으로 통일성 있게 전송
            try:
                if not settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE:
                    reason = "disabled_by_settings(SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE=false)"
                elif not (isinstance(result, dict) and result.get("success")):
                    reason = "economic_update_failed_or_skipped"
                elif updated == 0:
                    reason = "no_new_rows(updated_records=0)"
                else:
                    reason = f"unknown_condition(updated_records={updated})"
                notify_telegram_inference_skipped(
                    source="서버시작_추론",
                    reason=reason,
                    context={
                        "economic_success": bool((result or {}).get("success")) if isinstance(result, dict) else False,
                        "updated_records": updated,
                    },
                )
            except Exception:
                logger.warning("서버 시작: 추론 스킵 텔레그램 전송 실패(무시)", exc_info=True)
    except Exception as e:
        logger.exception("서버 시작: 추론 1회 실행 실패: %s", e)

    if settings.STARTUP_RUN_AUTO_BUY:
        try:
            logger.info("서버 시작: 자동 매수 1회 실행 (STARTUP_RUN_AUTO_BUY=true)")
            await asyncio.to_thread(run_auto_buy_now)
        except Exception as e:
            logger.exception("서버 시작: 자동 매수 1회 실행 실패: %s", e)
    else:
        logger.info("서버 시작: 자동 매수 스킵 (STARTUP_RUN_AUTO_BUY=false)")

    start_economic_data_scheduler()
    start_scheduler()
    start_sell_scheduler()
    logger.info(
        "스케줄러 기동 완료 — 경제(KST %s) / 매수(KST %s) / 매도(%s분) / EOD LLM(KST %s, enabled=%s)",
        settings.SCHEDULE_ECONOMIC_UPDATE_TIME,
        settings.SCHEDULE_AUTO_BUY_TIME,
        settings.SCHEDULE_AUTO_SELL_INTERVAL_MIN,
        settings.SCHEDULE_EOD_LLM_REPORT_TIME_KST,
        settings.SCHEDULE_EOD_LLM_REPORT_ENABLED,
    )
    ov = get_all_schedules_overview()
    logger.info("스케줄 오버뷰(설정/다음 실행): %s", ov)


if __name__ == "__main__":
    import os

    from uvicorn.config import LOG_LEVELS

    host = (os.getenv("BACKEND_HOST") or os.getenv("HOST") or "0.0.0.0").strip()
    port = int(os.getenv("BACKEND_PORT") or os.getenv("PORT") or "8000")
    reload_flag = (os.getenv("BACKEND_RELOAD") or os.getenv("RELOAD") or "true").strip().lower()
    reload_enabled = reload_flag in ("1", "true", "yes", "y", "on")

    _lvl = (os.getenv("LOG_LEVEL") or "info").strip().lower()
    if _lvl not in LOG_LEVELS:
        _lvl = "info"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=_lvl,
        log_config=None,
    )
