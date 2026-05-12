"""
매수·매도·경제 데이터·추론·EOD LLM 등 주기 작업 스케줄.

`schedule` + 백그라운드 스레드로 동작하며, `stock_scheduler.log` 에 로깅한다.
"""

# ─── 모듈 임포트 ───
import asyncio
import threading
import time  # noqa: F401  (일부 잡에서 사용)
import traceback
from datetime import datetime, timedelta

import pytz
import schedule

from app.utils.logger import get_logger
from alarm.notify import (
    notify_telegram_auto_sell_run,
    notify_telegram_economic_update,
    notify_telegram_inference_failure,
    notify_telegram_inference_success,
    notify_telegram_inference_skipped,
    notify_telegram_sentiment_update,
    notify_telegram_sentiment_skipped,
    notify_telegram_trading_job_exception,
)
from app.core.config import settings
from app.services.balance_service import (
    get_all_overseas_balances,
    get_current_price,
    order_overseas_stock,
    cancel_overseas_order,
    sync_holdings_to_db,
    sync_order_fills_to_db,
    sync_open_orders_to_db,
    sync_cash_usd_to_db,
    _get_cash_usd_via_psamount_best_effort,
)
from app.services.economic_service import update_economic_data_in_background
from app.services.stock_recommendation_service import StockRecommendationService
from app.services.equity_snapshot_service import save_equity_snapshot_if_due, snapshot_key_for_now

# ─── 로깅 ───

logger = get_logger("stock_scheduler")

# schedule 모듈의 전역 job 큐는 스레드 안전하지 않다. 주식 스케줄러 스레드와 경제/주가 스케줄러 스레드가
# 동시에 run_pending()을 호출하면 동일 잡(예: 매도)이 같은 시각에 두 번 실행될 수 있다.
_schedule_run_lock = threading.Lock()

# 정규장 1시간 스냅샷 중복 저장 방지(프로세스 메모리)
_last_equity_snapshot_key: str | None = None


def _run_equity_snapshot_hourly_market() -> None:
    """정규장(ET) 10분 간격으로 KIS→DB 동기화 후 스냅샷 저장(best-effort)."""
    global _last_equity_snapshot_key
    try:
        key = snapshot_key_for_now()
        if _last_equity_snapshot_key == key:
            return
        # 10분 단위 스냅샷은 DB가 최신이어야 의미가 있어, 스냅샷 직전에 KIS→DB 동기화를 best-effort로 수행한다.
        # 실패해도 스냅샷 저장 함수가 예외를 삼키도록 되어 있어, 전체 스케줄은 계속 돈다.
        try:
            sync_holdings_to_db()
        except Exception:
            logger.warning("equity_snapshot 전 holdings 동기화 실패(무시)", exc_info=True)
        try:
            sync_cash_usd_to_db(ovrs_excg_cd="NASD")
        except Exception:
            logger.warning("equity_snapshot 전 cash 동기화 실패(무시)", exc_info=True)
        r = save_equity_snapshot_if_due()
        if r.get("attempted") and r.get("saved"):
            _last_equity_snapshot_key = str(r.get("snapshot_key") or key)
    except Exception:
        logger.warning("equity_snapshot 잡 예외(무시)", exc_info=True)


def _persist_auto_sell_summary(summary: dict | None) -> None:
    """1분 매도 요약을 Supabase scheduler_minute_logs 에 저장 (실패해도 스케줄은 계속)."""
    if not summary:
        return
    if not settings.SCHEDULER_MINUTE_LOG_TO_SUPABASE:
        return
    try:
        from app.services.scheduler_minute_log_service import save_scheduler_minute_log

        save_scheduler_minute_log("auto_sell", summary)
    except Exception:
        logger.warning("auto_sell 분 로그 Supabase 저장 실패", exc_info=True)


def _cancel_jobs_named(job_name: str) -> None:
    """전역 schedule에서 job_func 이름이 job_name 인 잡을 모두 제거한다."""
    for job in list(schedule.jobs):
        fn = job.job_func
        if getattr(fn, "__name__", "") == job_name:
            schedule.cancel_job(job)


class StockScheduler:
    """주식 자동매매 스케줄러 클래스"""
    
    def __init__(self):
        self.recommendation_service = StockRecommendationService()
        self.running = False
        self.sell_running = False
        self.scheduler_thread = None
        self._sell_job = None
        self._sell_lock = threading.Lock()  # 동시 실행 방지
        self._last_not_market_hours_log_at: datetime | None = None
        self._prev_market_hours: bool | None = None  # 장 오픈/마감 전환 감지용

    @staticmethod
    def _calc_market_window(now_in_ny: datetime) -> tuple[bool, datetime, datetime]:
        """
        미국 정규장(ET) 기준 장중 여부 및 오늘(또는 다음 거래일) 장 시작/종료 시각을 반환.

        반환:
        - is_market_hours: 장중 여부 (09:30~16:00 ET, 월~금)
        - open_dt: (해당 거래일) 09:30 ET
        - close_dt: (해당 거래일) 16:00 ET
        """
        ny = pytz.timezone("America/New_York")
        n = now_in_ny.astimezone(ny)

        # "오늘" 기준 오픈/클로즈 시각
        open_dt = n.replace(hour=9, minute=30, second=0, microsecond=0)
        close_dt = n.replace(hour=16, minute=0, second=0, microsecond=0)

        wd = n.weekday()  # 0=월 ... 6=일
        is_weekday = 0 <= wd <= 4
        is_market_hours = bool(is_weekday and (open_dt <= n <= close_dt))
        return is_market_hours, open_dt, close_dt

    @staticmethod
    def _next_market_open(now_in_ny: datetime) -> datetime:
        """다음 미국 정규장 시작(09:30 ET)을 반환."""
        ny = pytz.timezone("America/New_York")
        n = now_in_ny.astimezone(ny)
        is_market_hours, open_dt, close_dt = StockScheduler._calc_market_window(n)

        # 장 시작 전이면 오늘 09:30
        if n < open_dt and 0 <= n.weekday() <= 4:
            return open_dt
        # 장중/장마감 후면 다음 거래일 09:30
        days = 1
        while True:
            cand = (open_dt + timedelta(days=days)).replace(hour=9, minute=30, second=0, microsecond=0)
            if 0 <= cand.weekday() <= 4:
                return cand
            days += 1
    
    def start(self):
        """매수 스케줄러 시작"""
        if self.running:
            logger.warning("매수 스케줄러가 이미 실행 중입니다.")
            return False
        
        # 한국 시간 기준 SCHEDULE_AUTO_BUY_TIME (KST, HH:MM)에 매수 작업 실행
        schedule.every().day.at(settings.SCHEDULE_AUTO_BUY_TIME).do(self._run_auto_buy)

        # 미국 정규장(ET) 1시간 스냅샷: 매 분 체크 후 "정각 + 30분"일 때만 저장
        schedule.every(1).minutes.do(_run_equity_snapshot_hourly_market)
        
        # 별도 스레드에서 스케줄러 실행
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        
        logger.info(
            "주식 자동매매 스케줄러가 시작되었습니다. 한국 시간 매일 %s(KST)에 매수 작업이 실행됩니다.",
            settings.SCHEDULE_AUTO_BUY_TIME,
        )
        ensure_eod_llm_report_daily_job_scheduled()
        return True
    
    def stop(self):
        """매수 스케줄러 중지"""
        if not self.running:
            logger.warning("매수 스케줄러가 실행 중이 아닙니다.")
            return False
        
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        # 매수 관련 작업 취소 (sell 스케줄러는 유지)
        buy_jobs = [job for job in schedule.jobs if job.job_func.__name__ == '_run_auto_buy']
        for job in buy_jobs:
            schedule.cancel_job(job)
        
        logger.info("매수 스케줄러가 중지되었습니다.")
        return True
    
    def start_sell_scheduler(self):
        """매도 스케줄러 시작"""
        if self.sell_running:
            logger.warning("매도 스케줄러가 이미 실행 중입니다.")
            return False

        # 기존 매도 잡 전부 제거(_sell_job 유실·리로드 잔여 등으로 동일 잡이 둘 이상 남는 경우 방지)
        if self._sell_job is not None:
            schedule.cancel_job(self._sell_job)
            self._sell_job = None
        _cancel_jobs_named("_run_auto_sell")
        self._sell_job = schedule.every(settings.SCHEDULE_AUTO_SELL_INTERVAL_MIN).minutes.do(self._run_auto_sell)
        
        # 스케줄러 스레드가 없으면 시작
        if not self.running and not self.scheduler_thread:
            self.scheduler_thread = threading.Thread(target=self._run_scheduler)
            self.scheduler_thread.daemon = True
            self.scheduler_thread.start()
        
        self.sell_running = True
        logger.info("매도 스케줄러가 시작되었습니다. 1분마다 매도 대상을 확인합니다.")
        ensure_eod_llm_report_daily_job_scheduled()
        return True
    
    def stop_sell_scheduler(self):
        """매도 스케줄러 중지"""
        if not self.sell_running:
            logger.warning("매도 스케줄러가 실행 중이 아닙니다.")
            return False
        
        if self._sell_job is not None:
            schedule.cancel_job(self._sell_job)
            self._sell_job = None
        _cancel_jobs_named("_run_auto_sell")

        self.sell_running = False
        
        # 매수, 매도 모두 중지된 경우 스레드 종료
        if not self.running and self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
            self.scheduler_thread = None
            
        logger.info("매도 스케줄러가 중지되었습니다.")
        return True
    
    def _run_scheduler(self):
        """스케줄러 백그라운드 실행 함수"""
        while self.running or self.sell_running:
            with _schedule_run_lock:
                schedule.run_pending()
            time.sleep(1)
    
    def _run_auto_buy(self, *, telegram_label: str | None = None):
        """자동 매수 실행 함수 - 스케줄링된 시간에 실행됨"""
        try:
            logger.info("자동 매수 작업 시작")
            summary = self._execute_auto_buy()
            logger.info("자동 매수 작업 완료")
            # 잔고 스냅샷 추가 (텔레그램 메시지 풍부화)
            try:
                summary["balance_snapshot"] = get_all_overseas_balances()
            except Exception as be:
                logger.warning("매수 후 잔고 조회 실패: %s", be)
                summary["balance_snapshot"] = None
            try:
                from alarm.notify import notify_telegram_auto_buy_run
                summary["telegram_sent"] = notify_telegram_auto_buy_run(summary, label=telegram_label)
            except Exception as te:
                summary["telegram_sent"] = False
                logger.warning("매수 텔레그램 전송 실패: %s", te)
            try:
                from app.services.daily_log_service import save_daily_buy_log
                save_daily_buy_log(summary)
            except Exception as de:
                logger.warning("매수 로그 DB 저장 실패: %s", de)
            return True
        except Exception as e:
            logger.error(f"자동 매수 작업 중 오류 발생: {str(e)}", exc_info=True)
            job_label = "자동 매수"
            if (telegram_label or "").strip():
                job_label = f"{job_label} {telegram_label.strip()}"
            notify_telegram_trading_job_exception(job_label, e)
            return False

    def _run_auto_sell(self):
        """자동 매도 실행 함수 - 1분마다 실행됨"""
        if not self._sell_lock.acquire(blocking=False):
            logger.warning("매도 작업이 이미 실행 중입니다. 건너뜁니다.")
            return False
        try:
            logger.info("자동 매도 작업 시작")
            summary = self._execute_auto_sell()
            logger.info("자동 매도 작업 완료")
            if summary.get("market_hours") is True:
                # 잔고 스냅샷 추가 (텔레그램 메시지 풍부화)
                try:
                    summary["balance_snapshot"] = get_all_overseas_balances()
                except Exception as be:
                    logger.warning("잔고 조회 실패(텔레그램용): %s", be)
                    summary["balance_snapshot"] = None
                # 장중: 후보 유무 무관하게 텔레그램 전송 + DB 저장
                try:
                    summary["telegram_sent"] = notify_telegram_auto_sell_run(summary)
                except Exception as te:
                    summary["telegram_sent"] = False
                    logger.error("자동 매도 텔레그램 전송 중 예외: %s", te, exc_info=True)
                _persist_auto_sell_summary(summary)
            # 장외: Telegram/DB 모두 스킵
            return True
        except Exception as e:
            logger.error(f"자동 매도 작업 중 오류 발생: {str(e)}", exc_info=True)
            notify_telegram_trading_job_exception("자동 매도", e)
            return False
        finally:
            self._sell_lock.release()

    def _execute_auto_sell(self) -> dict:
        """자동 매도 실행 로직. 매 실행 요약 dict 반환 (텔레그램용)."""
        now_in_korea = datetime.now(pytz.timezone("Asia/Seoul"))
        now_in_ny = datetime.now(pytz.timezone("America/New_York"))
        is_market_hours, open_dt_ny, close_dt_ny = self._calc_market_window(now_in_ny)
        next_open_ny = self._next_market_open(now_in_ny)
        next_open_kst = next_open_ny.astimezone(pytz.timezone("Asia/Seoul"))
        mins_to_open = int(max(0, (next_open_ny - now_in_ny).total_seconds()) // 60)

        # ── 장 오픈/마감 전환 감지 ─────────────────────────────────────────────
        just_opened = self._prev_market_hours is False and is_market_hours is True
        just_closed = self._prev_market_hours is True and is_market_hours is False
        self._prev_market_hours = is_market_hours

        # 장 마감 감지: 마지막 KIS→DB 최종 동기화 후 종료
        if just_closed:
            logger.info("장 마감 감지 — 최종 KIS→DB 동기화 실행")
            try:
                sync_holdings_to_db()
                sync_order_fills_to_db()
                sync_open_orders_to_db()
            except Exception:
                logger.warning("장 마감 최종 sync 실패", exc_info=True)

        summary: dict = {
            "job": "auto_sell",
            "ny_trading_date": now_in_ny.strftime("%Y-%m-%d"),
            "kst": now_in_korea.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "ny_et": now_in_ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "market_hours": is_market_hours,
            "market_open_ny": open_dt_ny.isoformat(),
            "market_close_ny": close_dt_ny.isoformat(),
            "next_market_open_ny": next_open_ny.isoformat(),
            "next_market_open_kst": next_open_kst.isoformat(),
            "minutes_to_next_open": mins_to_open,
            "items": [],
        }

        if not is_market_hours:
            # 장외에는 로그 스팸을 줄이되, 장 오픈 임박(5분 이내)이면 더 자주 남긴다.
            should_log = False
            if self._last_not_market_hours_log_at is None:
                should_log = True
            else:
                elapsed = (now_in_korea - self._last_not_market_hours_log_at).total_seconds()
                if mins_to_open <= 5:
                    should_log = elapsed >= 60  # 오픈 임박: 1분당 1회
                else:
                    should_log = elapsed >= 600  # 평상시: 10분당 1회

            if should_log:
                self._last_not_market_hours_log_at = now_in_korea
                logger.info(
                    "현재 시간 %s (뉴욕: %s)은 미국 장 시간이 아닙니다. 매도 작업을 건너뜁니다. 다음 장 시작: %s (KST %s, 약 %d분 후)",
                    now_in_korea.strftime("%Y-%m-%d %H:%M:%S"),
                    now_in_ny.strftime("%Y-%m-%d %H:%M:%S"),
                    next_open_ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    next_open_kst.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    mins_to_open,
                )
            summary["status"] = "skipped_not_market_hours"
            summary["success"] = True
            summary["candidate_count"] = 0
            return summary

        # 장중: KIS → Supabase 동기화 (장 오픈 첫 실행이면 즉시, 이후 매 인터벌마다)
        if just_opened:
            logger.info("장 오픈 감지 — 즉시 KIS→DB 동기화 실행")
        try:
            sync_holdings_to_db()
            sync_order_fills_to_db()
            sync_open_orders_to_db()
        except Exception:
            logger.warning("장중 KIS→DB 동기화 실패(스케줄은 계속)", exc_info=True)

        logger.info(
            f"미국 장 시간 확인: {now_in_korea.strftime('%Y-%m-%d %H:%M:%S')} (뉴욕: {now_in_ny.strftime('%Y-%m-%d %H:%M:%S')})"
        )

        sell_candidates_result = self.recommendation_service.get_stocks_to_sell()

        if not sell_candidates_result or not sell_candidates_result.get("sell_candidates"):
            logger.info("매도 대상 종목이 없습니다.")
            summary["status"] = "no_sell_candidates"
            summary["success"] = True
            summary["candidate_count"] = 0
            return summary

        sell_candidates = sell_candidates_result.get("sell_candidates", [])
        summary["candidate_count"] = len(sell_candidates)
        logger.info(f"매도 대상 종목 {len(sell_candidates)}개를 찾았습니다.")

        for candidate in sell_candidates:
            try:
                ticker = candidate["ticker"]
                stock_name = candidate["stock_name"]
                exchange_code = candidate["exchange_code"]
                quantity = candidate["quantity"]
                qty_sellable = candidate.get("qty_sellable", quantity)

                sell_reasons = candidate.get("sell_reasons", [])
                reasons_str = "; ".join(sell_reasons)
                logger.info(f"{stock_name}({ticker}) 매도 근거: {reasons_str}")

                # 매도가능수량 0 → 미체결 주문 있거나 T+1 잠금 → 스킵
                if qty_sellable <= 0:
                    logger.warning("%s(%s) 매도가능수량 0 — 미체결 주문 또는 T+1 잠금, 매도 건너뜀", stock_name, ticker)
                    summary["items"].append({
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "outcome": "skipped_not_sellable",
                        "sell_reasons": sell_reasons,
                        **{k: v for k, v in {"purchase_price": candidate.get("purchase_price"), "price_change_pct": candidate.get("price_change_percent")}.items()},
                    })
                    continue

                quantity = qty_sellable
                _cmeta = {
                    "purchase_price": candidate.get("purchase_price"),
                    "price_change_pct": candidate.get("price_change_percent"),
                    "tech_details": candidate.get("technical_sell_details"),
                    "sentiment_score": candidate.get("sentiment_score"),
                }

                api_exchange_code = exchange_code
                if exchange_code == "NASD":
                    api_exchange_code = "NAS"
                elif exchange_code == "NYSE":
                    api_exchange_code = "NYS"

                price_params = {
                    "AUTH": "",
                    "EXCD": api_exchange_code,
                    "SYMB": ticker,
                }

                logger.info(
                    f"{stock_name}({ticker}) 현재가 조회 요청. 거래소: {api_exchange_code}, 심볼: {ticker}"
                )
                price_result = get_current_price(price_params)

                if price_result.get("rt_cd") != "0":
                    msg1 = price_result.get("msg1", "알 수 없는 오류")
                    logger.error(f"{stock_name}({ticker}) 현재가 조회 실패: {msg1}")
                    summary["items"].append(
                        {
                            "ticker": ticker,
                            "stock_name": stock_name,
                            "outcome": "price_fetch_failed",
                            "error": msg1,
                            "sell_reasons": sell_reasons,
                            **_cmeta,
                        }
                    )
                    if "초당" in str(msg1):
                        time.sleep(3)
                    continue

                last_price = price_result.get("output", {}).get("last", "")
                try:
                    if not last_price or last_price == "":
                        logger.error(
                            f"{stock_name}({ticker}) 현재가가 비어있습니다. 다음 API 호출에서 다시 시도합니다."
                        )
                        summary["items"].append(
                            {
                                "ticker": ticker,
                                "stock_name": stock_name,
                                "outcome": "price_empty",
                                "sell_reasons": sell_reasons,
                                **_cmeta,
                            }
                        )
                        time.sleep(2)
                        continue

                    current_price = float(last_price)

                    if current_price <= 0:
                        logger.error(f"{stock_name}({ticker}) 현재가가 유효하지 않습니다: {current_price}")
                        summary["items"].append(
                            {
                                "ticker": ticker,
                                "stock_name": stock_name,
                                "outcome": "invalid_price",
                                "current_price": current_price,
                                "sell_reasons": sell_reasons,
                                **_cmeta,
                            }
                        )
                        continue
                except ValueError as ve:
                    logger.error(f"{stock_name}({ticker}) 현재가 변환 오류: {str(ve)}, 값: '{last_price}'")
                    summary["items"].append(
                        {
                            "ticker": ticker,
                            "stock_name": stock_name,
                            "outcome": "price_parse_error",
                            "error": str(ve),
                            "raw_last": str(last_price),
                            "sell_reasons": sell_reasons,
                            **_cmeta,
                        }
                    )
                    continue

                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "OVRS_EXCG_CD": exchange_code,
                    "PDNO": ticker,
                    "ORD_DVSN": "00",
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(current_price),
                    "is_buy": False,
                }

                logger.info(f"{stock_name}({ticker}) 매도 주문 실행: 수량 {quantity}주, 가격 ${current_price}")
                order_result = order_overseas_stock(order_data)
                msg1 = order_result.get("msg1", "") if isinstance(order_result, dict) else ""
                order_success = bool(isinstance(order_result, dict) and order_result.get("rt_cd") == "0")

                try:
                    from app.services.daily_log_service import save_order
                    save_order(
                        side="sell",
                        ticker=ticker,
                        stock_name=stock_name,
                        exchange_code=exchange_code,
                        quantity=quantity,
                        limit_price=current_price,
                        rt_cd=order_result.get("rt_cd"),
                        api_message=msg1,
                        success=order_success,
                        source="auto_sell",
                        payload={
                            "reason": "sell_candidates(strategy_rules)",
                            "sell_reasons": sell_reasons,
                            "meta": _cmeta,
                            "order_result": order_result,
                            "order_request": order_data,
                        },
                        ny_trading_date=now_in_ny.strftime("%Y-%m-%d"),
                    )
                except Exception as oe:
                    logger.warning("order_history 저장 실패: %s", oe)

                if order_success:
                    logger.info(f"{stock_name}({ticker}) 매도 주문 성공: {msg1 or '주문이 접수되었습니다.'}")
                    summary["items"].append(
                        {
                            "ticker": ticker,
                            "stock_name": stock_name,
                            "outcome": "order_success",
                            "quantity": quantity,
                            "limit_price": current_price,
                            "exchange_code": exchange_code,
                            "api_message": msg1,
                            "sell_reasons": sell_reasons,
                            **_cmeta,
                        }
                    )
                else:
                    logger.error(f"{stock_name}({ticker}) 매도 주문 실패: {msg1 or '알 수 없는 오류'}")
                    summary["items"].append(
                        {
                            "ticker": ticker,
                            "stock_name": stock_name,
                            "outcome": "order_failed",
                            "quantity": quantity,
                            "limit_price": current_price,
                            "exchange_code": exchange_code,
                            "error": msg1 or "알 수 없는 오류",
                            "sell_reasons": sell_reasons,
                            **_cmeta,
                        }
                    )

                time.sleep(2)

            except Exception as e:
                logger.error(
                    f"{candidate['stock_name']}({candidate['ticker']}) 매도 처리 중 오류: {str(e)}",
                    exc_info=True,
                )
                summary["items"].append(
                    {
                        "ticker": candidate.get("ticker"),
                        "stock_name": candidate.get("stock_name"),
                        "outcome": "candidate_exception",
                        "error": str(e),
                    }
                )
                time.sleep(1)

        logger.info("자동 매도 처리가 완료되었습니다.")
        # 주문 직후 DB도 최대한 최신 상태로 맞춰둔다(체결/미체결 반영 지연 최소화)
        try:
            sync_holdings_to_db()
            sync_order_fills_to_db()
            sync_open_orders_to_db()
            # 마지막 단계: KIS 매수가능금액 기반 현금(USD)도 갱신
            sync_cash_usd_to_db(ovrs_excg_cd="NASD")
        except Exception:
            logger.warning("매도 후 KIS→DB 재동기화 실패(무시)", exc_info=True)
        summary["status"] = "completed"
        bad = {"order_failed", "candidate_exception"}
        summary["success"] = not any((it.get("outcome") in bad) for it in summary["items"])
        summary["had_price_or_validation_issue"] = any(
            it.get("outcome")
            in ("price_fetch_failed", "price_empty", "invalid_price", "price_parse_error")
            for it in summary["items"]
        )
        return summary
    
    def _execute_manual_sell(self, tickers: list) -> dict:
        """지정 티커만 즉시 매도. 전략 룰 무관하게 강제 매도."""
        import time as _time
        from app.services.balance_service import get_all_overseas_balances, get_current_price, order_overseas_stock
        from app.services.daily_log_service import save_order

        now_ny = datetime.now(pytz.timezone("America/New_York"))
        now_kst = datetime.now(pytz.timezone("Asia/Seoul"))

        summary: dict = {
            "job": "manual_sell",
            "ny_trading_date": now_ny.strftime("%Y-%m-%d"),
            "kst": now_kst.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "ny_et": now_ny.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "candidate_count": len(tickers),
            "items": [],
        }

        balance_result = get_all_overseas_balances()
        if balance_result.get("rt_cd") != "0":
            summary["status"] = "balance_fetch_failed"
            summary["success"] = False
            return summary

        holdings_by_ticker = {
            item["ovrs_pdno"]: item
            for item in balance_result.get("output1", [])
            if item.get("ovrs_pdno")
        }

        for ticker in tickers:
            holding = holdings_by_ticker.get(ticker)
            if not holding:
                logger.warning("수동 매도: %s 보유 종목 없음 — 건너뜀", ticker)
                summary["items"].append({"ticker": ticker, "outcome": "not_holding"})
                continue

            stock_name = holding.get("ovrs_item_name", ticker)
            exchange_code = holding.get("ovrs_excg_cd", "NASD")
            quantity = int(float(holding.get("ord_psbl_qty") or holding.get("ovrs_cblc_qty", 0)))

            if quantity <= 0:
                logger.warning("수동 매도: %s 매도가능 수량 0 — 건너뜀", ticker)
                summary["items"].append({"ticker": ticker, "stock_name": stock_name, "outcome": "zero_quantity"})
                continue

            api_exchange_code = "NAS" if exchange_code == "NASD" else ("NYS" if exchange_code == "NYSE" else exchange_code)
            price_result = get_current_price({"AUTH": "", "EXCD": api_exchange_code, "SYMB": ticker})

            if price_result.get("rt_cd") != "0":
                msg = price_result.get("msg1", "")
                logger.error("수동 매도: %s 현재가 조회 실패 — %s", ticker, msg)
                summary["items"].append({"ticker": ticker, "stock_name": stock_name, "outcome": "price_fetch_failed", "error": msg})
                continue

            last = price_result.get("output", {}).get("last", "")
            try:
                current_price = float(last)
            except (ValueError, TypeError):
                summary["items"].append({"ticker": ticker, "stock_name": stock_name, "outcome": "price_parse_error", "raw_last": str(last)})
                continue

            order_data = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": exchange_code,
                "PDNO": ticker,
                "ORD_DVSN": "00",
                "ORD_QTY": str(quantity),
                "OVRS_ORD_UNPR": str(current_price),
                "is_buy": False,
            }

            order_result = order_overseas_stock(order_data)
            msg1 = order_result.get("msg1", "") if isinstance(order_result, dict) else ""
            order_success = bool(isinstance(order_result, dict) and order_result.get("rt_cd") == "0")

            try:
                save_order(
                    side="sell",
                    ticker=ticker,
                    stock_name=stock_name,
                    exchange_code=exchange_code,
                    quantity=quantity,
                    limit_price=current_price,
                    rt_cd=order_result.get("rt_cd") if isinstance(order_result, dict) else None,
                    api_message=msg1,
                    success=order_success,
                    source="manual_sell",
                    payload={"reason": "manual_sell", "order_result": order_result, "order_request": order_data},
                    ny_trading_date=now_ny.strftime("%Y-%m-%d"),
                )
            except Exception as oe:
                logger.warning("수동 매도 order_history 저장 실패: %s", oe)

            outcome = "order_success" if order_success else "order_failed"
            summary["items"].append({
                "ticker": ticker,
                "stock_name": stock_name,
                "outcome": outcome,
                "quantity": quantity,
                "limit_price": current_price,
                "exchange_code": exchange_code,
                "api_message": msg1,
                "sell_reasons": ["manual_sell"],
            })
            logger.info("수동 매도 %s(%s) %s — %s", stock_name, ticker, outcome, msg1)
            _time.sleep(2)

        try:
            sync_holdings_to_db()
            sync_order_fills_to_db()
            sync_open_orders_to_db()
            sync_cash_usd_to_db(ovrs_excg_cd="NASD")
        except Exception:
            logger.warning("수동 매도 후 KIS→DB 재동기화 실패(무시)", exc_info=True)

        summary["status"] = "completed"
        summary["success"] = not any(it.get("outcome") == "order_failed" for it in summary["items"])
        return summary

    def _execute_auto_buy(self) -> dict:
        """자동 매수 실행 로직. 실행 요약 dict 반환."""
        now_kst = datetime.now(pytz.timezone("Asia/Seoul"))
        now_ny = datetime.now(pytz.timezone("America/New_York"))
        summary: dict = {
            "job": "auto_buy",
            "ny_trading_date": now_ny.strftime("%Y-%m-%d"),
            "kst": now_kst.isoformat(),
            "candidate_count": 0,
            "ordered_count": 0,
            "items": [],
            "status": "completed",
            "success": True,
            "telegram_sent": False,
        }

        try:
            balance_result = get_all_overseas_balances()
            if balance_result.get("rt_cd") != "0":
                logger.error(f"보유 종목 조회 실패: {balance_result.get('msg1', '알 수 없는 오류')}")
                summary["status"] = "balance_error"
                summary["success"] = False
                return summary

            holdings = balance_result.get("output1", [])
            holding_tickers = {item.get("ovrs_pdno") for item in holdings if item.get("ovrs_pdno")}
            logger.info(f"현재 보유 중인 종목 수: {len(holding_tickers)}")
        except Exception as e:
            logger.error(f"보유 종목 조회 중 오류 발생: {str(e)}", exc_info=True)
            summary["status"] = "balance_exception"
            summary["success"] = False
            return summary

        # 매수 가능 USD 잔고 사전 확인 (remaining_cash: KIS 실시간, initial_cash_usd: DB 시드 고정값)
        try:
            cash_usd, _ = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd="NASD")
            summary["cash_usd"] = cash_usd
            if cash_usd is None or cash_usd <= 0:
                logger.warning("매수 가능 잔고 없음 (cash_usd=%s) — 매수 중단", cash_usd)
                summary["status"] = "insufficient_balance"
                summary["success"] = False
                return summary
            remaining_cash = cash_usd
            logger.info("매수 가능 잔고: $%.2f", remaining_cash)
        except Exception as e:
            logger.warning("잔고 사전 확인 실패 — KIS 거절에 의존해 진행: %s", e)
            remaining_cash = None

        # 포지션 크기 계산 기준: DB에 저장된 시드(initial_cash_usd) — 매매 후 변하지 않는 고정값
        try:
            from app.db.supabase import supabase as _supa
            _seed_resp = _supa.table("holdings_summary").select("initial_cash_usd").eq("id", "main").limit(1).execute()
            initial_cash_usd = float(_seed_resp.data[0]["initial_cash_usd"]) if _seed_resp.data else None
            logger.info("DB 시드 기준값: $%.2f", initial_cash_usd or 0)
        except Exception as e:
            logger.warning("DB 시드 조회 실패 — 현재 잔고로 대체: %s", e)
            initial_cash_usd = remaining_cash

        try:
            self.recommendation_service.generate_technical_recommendations()
        except Exception as te:
            logger.warning("매수 전 기술적 지표 갱신 실패(기존 DB 값으로 진행): %s", te)

        recommendations = self.recommendation_service.get_combined_recommendations_with_technical_and_sentiment()

        if not recommendations or not recommendations.get("results"):
            logger.info("매수 대상 종목이 없습니다.")
            summary["status"] = "no_candidates"
            return summary

        buy_candidates = recommendations.get("results", [])
        summary["candidate_count"] = len(buy_candidates)
        logger.info(f"매수 대상 종목 {len(buy_candidates)}개를 찾았습니다.")

        from app.services.daily_log_service import save_order

        for candidate in buy_candidates:
            try:
                ticker = candidate["ticker"]
                stock_name = candidate["stock_name"]
                _bmeta = {
                    "accuracy": candidate.get("accuracy"),
                    "rise_probability": candidate.get("rise_probability"),
                    "sentiment_score": candidate.get("sentiment_score"),
                    "rsi": candidate.get("rsi"),
                    "golden_cross": candidate.get("golden_cross"),
                    "macd_buy_signal": candidate.get("macd_buy_signal"),
                    "composite_score": candidate.get("composite_score"),
                }

                if ticker.endswith(".X") or ticker.endswith(".N"):
                    exchange_code = "NYSE" if ticker.endswith(".N") else "NASD"
                    pure_ticker = ticker.split(".")[0]
                else:
                    exchange_code = "NASD"
                    pure_ticker = ticker

                if pure_ticker in holding_tickers:
                    logger.info(f"{stock_name}({ticker}) - 이미 보유 중인 종목이므로 매수하지 않습니다.")
                    summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "already_holding"})
                    continue

                api_exchange_code = "NYS" if exchange_code == "NYSE" else "NAS"
                price_result = get_current_price({"AUTH": "", "EXCD": api_exchange_code, "SYMB": pure_ticker})

                if price_result.get("rt_cd") != "0":
                    msg1 = price_result.get("msg1", "알 수 없는 오류")
                    logger.error(f"{stock_name}({ticker}) 현재가 조회 실패: {msg1}")
                    summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "price_fetch_failed", "error": msg1})
                    summary["success"] = False
                    continue

                current_price = float(price_result.get("output", {}).get("last", 0))
                if current_price <= 0:
                    logger.error(f"{stock_name}({ticker}) 현재가가 유효하지 않습니다: {current_price}")
                    summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "invalid_price"})
                    summary["success"] = False
                    continue

                buy_amount_usd = (initial_cash_usd or 0) * settings.TRADING_BUY_PCT_OF_CASH
                if buy_amount_usd <= 0 or current_price <= 0:
                    logger.warning("%s(%s) 매수 금액 산출 불가 (seed=%.2f, pct=%.2f) — 건너뜀", stock_name, ticker, initial_cash_usd or 0, settings.TRADING_BUY_PCT_OF_CASH)
                    summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "invalid_buy_amount"})
                    continue
                quantity = max(1, int(buy_amount_usd // current_price))

                # 잔고 부족 사전 차단
                estimated_cost = current_price * quantity
                if remaining_cash is not None and remaining_cash < estimated_cost:
                    logger.warning(
                        "%s(%s) 잔고 부족 — 필요 $%.2f, 남은 잔고 $%.2f → 매수 건너뜀",
                        stock_name, ticker, estimated_cost, remaining_cash,
                    )
                    summary["items"].append({
                        "ticker": pure_ticker,
                        "stock_name": stock_name,
                        "outcome": "insufficient_balance",
                        "required_usd": estimated_cost,
                        "remaining_cash_usd": remaining_cash,
                        **_bmeta,
                    })
                    summary["success"] = False
                    continue

                order_data = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "OVRS_EXCG_CD": exchange_code,
                    "PDNO": pure_ticker,
                    "ORD_DVSN": settings.TRADING_ORDER_TYPE,
                    "ORD_QTY": str(quantity),
                    "OVRS_ORD_UNPR": str(current_price),
                    "is_buy": True,
                }

                logger.info(f"{stock_name}({ticker}) 매수 주문 실행: 수량 {quantity}주, 가격 ${current_price}")
                order_result = order_overseas_stock(order_data)
                msg1 = order_result.get("msg1", "") if isinstance(order_result, dict) else ""
                order_success = bool(isinstance(order_result, dict) and order_result.get("rt_cd") == "0")

                if order_success:
                    # 매수 접수 후 실제 보유 반영 여부 확인 (최대 3회 × 4s = 12s)
                    odno = (order_result.get("output") or {}).get("ODNO", "")
                    holding_verified = False
                    for _attempt in range(3):
                        time.sleep(4)
                        _vr = get_all_overseas_balances()
                        if _vr.get("rt_cd") == "0":
                            _vt = {h.get("ovrs_pdno") for h in _vr.get("output1", [])}
                            if pure_ticker in _vt:
                                holding_verified = True
                                break

                    if holding_verified:
                        logger.info(f"{stock_name}({ticker}) 매수 주문 성공 및 보유 확인 완료: {msg1 or '주문이 접수되었습니다.'}")
                        save_order(
                            side="buy",
                            ticker=pure_ticker,
                            stock_name=stock_name,
                            exchange_code=exchange_code,
                            quantity=quantity,
                            limit_price=current_price,
                            order_type=settings.TRADING_ORDER_TYPE,
                            rt_cd=order_result.get("rt_cd"),
                            api_message=msg1,
                            success=True,
                            source="auto_buy",
                            payload={
                                "reason": "combined_recommendation(technical+sentiment+ai)",
                                "meta": _bmeta,
                                "order_result": order_result,
                                "order_request": order_data,
                            },
                            ny_trading_date=now_ny.strftime("%Y-%m-%d"),
                        )
                        summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "order_success", "quantity": quantity, "limit_price": current_price, "exchange_code": exchange_code, "api_message": msg1, **_bmeta})
                        summary["ordered_count"] = summary.get("ordered_count", 0) + 1
                        if remaining_cash is not None:
                            remaining_cash -= estimated_cost
                    else:
                        # 주문은 접수됐으나 보유 미반영 → 취소 시도
                        logger.error(
                            "%s(%s) 매수 후 보유 미반영 (ODNO=%s) — 취소 시도",
                            stock_name, ticker, odno,
                        )
                        cancel_result = {}
                        if odno:
                            cancel_result = cancel_overseas_order(
                                exchange_code=exchange_code,
                                ticker=pure_ticker,
                                orgn_odno=odno,
                            )
                            logger.error(
                                "%s(%s) 취소 결과: rt_cd=%s msg=%s",
                                stock_name, ticker,
                                cancel_result.get("rt_cd"),
                                cancel_result.get("msg1"),
                            )
                        cancel_msg = cancel_result.get("msg1", "") if cancel_result else ""
                        save_order(
                            side="buy",
                            ticker=pure_ticker,
                            stock_name=stock_name,
                            exchange_code=exchange_code,
                            quantity=quantity,
                            limit_price=current_price,
                            order_type=settings.TRADING_ORDER_TYPE,
                            rt_cd=order_result.get("rt_cd"),
                            api_message=f"order_unconfirmed_canceled (취소: {cancel_msg})",
                            success=False,
                            source="auto_buy",
                            payload={
                                "reason": "combined_recommendation(technical+sentiment+ai)",
                                "meta": _bmeta,
                                "order_result": order_result,
                                "order_request": order_data,
                                "cancel_result": cancel_result,
                                "odno": odno,
                            },
                            ny_trading_date=now_ny.strftime("%Y-%m-%d"),
                        )
                        summary["items"].append({
                            "ticker": pure_ticker,
                            "stock_name": stock_name,
                            "outcome": "order_unconfirmed_canceled",
                            "odno": odno,
                            "cancel_rt_cd": cancel_result.get("rt_cd"),
                            "cancel_msg": cancel_result.get("msg1"),
                            "exchange_code": exchange_code,
                            **_bmeta,
                        })
                        summary["success"] = False
                else:
                    logger.error(f"{stock_name}({ticker}) 매수 주문 실패: {msg1 or '알 수 없는 오류'}")
                    save_order(
                        side="buy",
                        ticker=pure_ticker,
                        stock_name=stock_name,
                        exchange_code=exchange_code,
                        quantity=quantity,
                        limit_price=current_price,
                        order_type=settings.TRADING_ORDER_TYPE,
                        rt_cd=order_result.get("rt_cd"),
                        api_message=msg1,
                        success=False,
                        source="auto_buy",
                        payload={
                            "reason": "combined_recommendation(technical+sentiment+ai)",
                            "meta": _bmeta,
                            "order_result": order_result,
                            "order_request": order_data,
                        },
                        ny_trading_date=now_ny.strftime("%Y-%m-%d"),
                    )
                    summary["items"].append({"ticker": pure_ticker, "stock_name": stock_name, "outcome": "order_failed", "error": msg1, "exchange_code": exchange_code, **_bmeta})
                    summary["success"] = False

                time.sleep(1)

            except Exception as e:
                logger.error(f"{candidate['stock_name']}({candidate['ticker']}) 매수 처리 중 오류: {str(e)}", exc_info=True)
                summary["items"].append({"ticker": candidate.get("ticker"), "stock_name": candidate.get("stock_name"), "outcome": "candidate_exception", "error": str(e)})
                summary["success"] = False

        logger.info("자동 매수 처리가 완료되었습니다.")
        try:
            sync_holdings_to_db()
            sync_order_fills_to_db()
            sync_open_orders_to_db()
            sync_cash_usd_to_db(ovrs_excg_cd="NASD")
        except Exception:
            logger.warning("매수 후 KIS→DB 재동기화 실패(무시)", exc_info=True)
        return summary

# 싱글톤 인스턴스 생성
stock_scheduler = StockScheduler()

_eod_llm_report_daily_registered = False


def _run_eod_llm_report_daily() -> None:
    try:
        from app.services.eod_llm_report_service import run_eod_llm_report_daily

        run_eod_llm_report_daily()
    except Exception as e:
        logger.error("EOD LLM 리포트 실행 중 예외: %s", e, exc_info=True)


def ensure_eod_llm_report_daily_job_scheduled() -> None:
    """전역 schedule 에 EOD LLM 일일 리포트 잡을 한 번만 등록한다 (매일 KST 1회)."""
    global _eod_llm_report_daily_registered
    if _eod_llm_report_daily_registered:
        return
    hhmm = (settings.SCHEDULE_EOD_LLM_REPORT_TIME_KST or "07:00").strip()
    schedule.every().day.at(hhmm).do(_run_eod_llm_report_daily)
    _eod_llm_report_daily_registered = True
    logger.info("EOD LLM 일일 리포트 잡 등록 (매일 KST %s, Supabase 분 로그 필터 → Upstage)", hhmm)


def start_scheduler():
    """매수 스케줄러 시작 함수"""
    return stock_scheduler.start()

def stop_scheduler():
    """매수 스케줄러 중지 함수"""
    return stock_scheduler.stop()

def start_sell_scheduler():
    """매도 스케줄러 시작 함수"""
    return stock_scheduler.start_sell_scheduler()

def stop_sell_scheduler():
    """매도 스케줄러 중지 함수"""
    return stock_scheduler.stop_sell_scheduler()

def _next_kst_daily_run_iso(hhmm: str) -> str:
    """설정된 KST 시각의 다음 발생 시각을 ISO8601 로 반환."""
    kst = pytz.timezone("Asia/Seoul")
    now = datetime.now(kst)
    parts = (hhmm or "00:00").strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.isoformat()


def _next_sell_check_iso() -> str | None:
    """매도 스케줄러가 장중 점검할 때까지 남은 시간 기준 다음 분(뉴욕) — 장외면 None."""
    ny = pytz.timezone("America/New_York")
    now_ny = datetime.now(ny)
    wd = now_ny.weekday()
    if wd > 4:
        return None
    hm = now_ny.hour * 60 + now_ny.minute
    open_m = 9 * 60 + 30
    close_m = 16 * 60
    if hm < open_m or hm >= close_m:
        return None
    nxt = (now_ny.replace(second=0, microsecond=0) + timedelta(minutes=1))
    if nxt.hour == 16 and nxt.minute > 0:
        return None
    return nxt.astimezone(pytz.UTC).isoformat()


def get_scheduler_status():
    """스케줄러 상태·다음 매수 시각(KST)·다음 매도 점검 시각(뉴욕 장중)"""
    buy_running = stock_scheduler.running
    sell_running = stock_scheduler.sell_running
    next_buy_at = _next_kst_daily_run_iso(settings.SCHEDULE_AUTO_BUY_TIME)
    next_sell_at = _next_sell_check_iso() if sell_running else None
    msg = (
        f"매수 스케줄러: {'실행 중' if buy_running else '중지됨'}, "
        f"매도 스케줄러: {'실행 중' if sell_running else '중지됨'}"
    )
    return {
        "buy_running": buy_running,
        "sell_running": sell_running,
        "message": msg,
        "schedule_buy_time_kst": settings.SCHEDULE_AUTO_BUY_TIME,
        "schedule_sell_interval_min": settings.SCHEDULE_AUTO_SELL_INTERVAL_MIN,
        "next_auto_buy_at": next_buy_at,
        "next_sell_check_at": next_sell_at,
        "is_mock": settings.KIS_USE_MOCK,
    }


def get_all_schedules_overview() -> dict:
    """
    서버 기동 시점 로그/상태 확인용: 현재 설정된 스케줄 요약 + 다음 실행 예정 시각.

    - KST 기반 일일 잡(경제/매수/EOD LLM)은 다음 실행 시각을 ISO(KST)로 계산
    - 매도 1분 체크는 장중일 때만 다음 점검(UTC ISO) 반환 (장외면 None)
    """
    buy_running = stock_scheduler.running
    sell_running = stock_scheduler.sell_running
    econ_running = bool(economic_data_scheduler_running)

    econ_hhmm = (settings.SCHEDULE_ECONOMIC_UPDATE_TIME or "").strip()
    buy_hhmm = (settings.SCHEDULE_AUTO_BUY_TIME or "").strip()
    eod_hhmm = (settings.SCHEDULE_EOD_LLM_REPORT_TIME_KST or "").strip()

    next_econ_at = _next_kst_daily_run_iso(econ_hhmm or "00:00")
    next_buy_at = _next_kst_daily_run_iso(buy_hhmm or "00:00")
    next_eod_at = _next_kst_daily_run_iso(eod_hhmm or "00:00")
    next_sell_at = _next_sell_check_iso() if sell_running else None

    return {
        "economic_update": {
            "running": econ_running,
            "time_kst": econ_hhmm,
            "after_run_inference": bool(settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE),
            "next_run_at_kst": next_econ_at,
        },
        "model_inference": {
            "enabled": bool(settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE),
            "trigger": "after_economic_update_if_new_rows",
        },
        "auto_buy": {
            "running": buy_running,
            "time_kst": buy_hhmm,
            "next_run_at_kst": next_buy_at,
        },
        "auto_sell": {
            "running": sell_running,
            "interval_min": int(settings.SCHEDULE_AUTO_SELL_INTERVAL_MIN),
            "next_check_at_utc": next_sell_at,
            "note": "장중에만 점검 실행",
        },
        "eod_llm_report": {
            "enabled": bool(settings.SCHEDULE_EOD_LLM_REPORT_ENABLED),
            "time_kst": eod_hhmm,
            "next_run_at_kst": next_eod_at,
        },
    }

def run_auto_buy_now():
    """즉시 매수 실행 함수 (테스트용)"""
    stock_scheduler._run_auto_buy()


def run_manual_buy_now():
    """수동 매수 실행 함수 (관리자용) — 텔레그램에 (수동 매수) 라벨을 포함."""
    stock_scheduler._run_auto_buy(telegram_label="(수동 매수)")
    
def run_auto_sell_now():
    """즉시 매도 실행 함수 (테스트용)"""
    stock_scheduler._run_auto_sell()

def run_manual_sell_now(tickers: list) -> dict:
    """수동 매도 실행 함수 (관리자용) — 지정 티커만 즉시 매도, 텔레그램 알림 포함."""
    from alarm.notify import notify_telegram_auto_sell_run
    summary = stock_scheduler._execute_manual_sell(tickers)
    try:
        summary["balance_snapshot"] = get_all_overseas_balances()
    except Exception:
        summary["balance_snapshot"] = None
    try:
        summary["telegram_sent"] = notify_telegram_auto_sell_run(summary)
    except Exception as te:
        summary["telegram_sent"] = False
        logger.warning("수동 매도 텔레그램 전송 실패: %s", te)
    return summary

# 경제 데이터 스케줄러 관련 변수 및 함수
economic_data_scheduler_running = False
economic_data_scheduler_thread = None

def _run_economic_data_update(telegram_source: str = "경제스케줄"):
    """경제·주가 DB 갱신 후, 신규 행이 있으면 저장 모델로 추론·예측 테이블 갱신."""
    elog = get_logger("economic_scheduler")
    try:
        elog.info("경제 데이터 업데이트 작업 시작")
        result = asyncio.run(update_economic_data_in_background())
        elog.info("경제 데이터 업데이트 작업 완료: %s", result)

        rdict = result if isinstance(result, dict) else {}
        econ_tg_sent = notify_telegram_economic_update(rdict, source=telegram_source)

        from app.services.daily_log_service import save_daily_economic_log, save_daily_inference_log
        save_daily_economic_log(rdict, telegram_sent=econ_tg_sent)

        updated = int((rdict).get("updated_records") or 0)
        if (
            settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE
            and rdict.get("success")
            and updated > 0
        ):
            elog.info("신규 저장 행 %s건 → 모델 추론 및 predicted_stocks / stock_analysis_results 갱신", updated)
            try:
                from app.services.ml_inference_client import trigger_inference

                inf = trigger_inference()
                elog.info("추론·DB 갱신 완료: %s", inf)
                inf_tg_sent = notify_telegram_inference_success(inf, source=f"{telegram_source}_추론")
                save_daily_inference_log(inf or {}, telegram_sent=inf_tg_sent)
            except Exception as inf_e:
                elog.error(
                    "추론·DB 갱신 실패(경제 데이터는 이미 저장됨): %s",
                    inf_e,
                    exc_info=True,
                )
                inf_tg_sent = notify_telegram_inference_failure(inf_e, source=f"{telegram_source}_추론")
                save_daily_inference_log({"error": str(inf_e)}, telegram_sent=inf_tg_sent)
        else:
            # 실행 조건이 안 맞아도 결과를 텔레그램으로 통일성 있게 전송한다.
            if not settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE:
                reason = "disabled_by_settings(SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE=false)"
            elif not rdict.get("success"):
                reason = "economic_update_failed_or_skipped"
            elif updated == 0:
                reason = "no_new_rows(updated_records=0)"
            else:
                reason = f"unknown_condition(updated_records={updated})"
            elog.info("추론 스킵: %s", reason)
            try:
                notify_telegram_inference_skipped(
                    source=f"{telegram_source}_추론",
                    reason=reason,
                    context={
                        "economic_success": bool(rdict.get("success")),
                        "updated_records": updated,
                    },
                )
            except Exception:
                elog.warning("추론 스킵 텔레그램 전송 실패(무시)", exc_info=True)

        if rdict.get("success"):
            try:
                from app.services.stock_recommendation_service import (
                    StockRecommendationService,
                    has_today_sentiment_data_kst,
                )
                if has_today_sentiment_data_kst():
                    elog.info("뉴스 감성 분석 스킵 — 오늘(KST) 데이터 이미 존재")
                    try:
                        notify_telegram_sentiment_skipped(
                            source=telegram_source,
                            reason="already_loaded_today_kst",
                            context={"today_loaded": True},
                        )
                    except Exception:
                        elog.warning("감성 스킵 텔레그램 전송 실패(무시)", exc_info=True)
                else:
                    elog.info("뉴스 감성 분석 시작 (장 열리기 전 최신 뉴스 갱신)")
                    sent_result = StockRecommendationService().fetch_and_store_sentiment_for_recommendations()
                    elog.info("뉴스 감성 분석 완료: %s", sent_result)
                    notify_telegram_sentiment_update(sent_result or {}, source=telegram_source)
            except Exception as sent_e:
                elog.error("뉴스 감성 분석 실패 (스케줄 계속): %s", sent_e, exc_info=True)
                notify_telegram_sentiment_update({"error": str(sent_e)}, source=telegram_source)
        else:
            # 경제 업데이트가 실패/스킵이면 감성도 실행되지 않으므로 스킵 결과를 통일성 있게 전송한다.
            try:
                notify_telegram_sentiment_skipped(
                    source=telegram_source,
                    reason="economic_update_failed_or_skipped",
                    context={"economic_success": bool(rdict.get("success"))},
                )
            except Exception:
                elog.warning("감성 스킵 텔레그램 전송 실패(무시)", exc_info=True)

        return True
    except Exception as e:
        elog.error("경제 데이터 업데이트 작업 중 오류 발생: %s", e, exc_info=True)
        econ_tg_sent = notify_telegram_economic_update(
            {"success": False, "error": str(e), "traceback": traceback.format_exc()},
            source=telegram_source,
        )
        try:
            from app.services.daily_log_service import save_daily_economic_log
            save_daily_economic_log({"success": False, "error": str(e)}, telegram_sent=econ_tg_sent)
        except Exception:
            pass
        return False

def _run_economic_scheduler():
    """경제 데이터 스케줄러 백그라운드 실행 함수"""
    global economic_data_scheduler_running
    while economic_data_scheduler_running:
        with _schedule_run_lock:
            schedule.run_pending()
        time.sleep(1)

def start_economic_data_scheduler():
    """경제 데이터 업데이트 스케줄러 시작 함수"""
    global economic_data_scheduler_running, economic_data_scheduler_thread
    
    if economic_data_scheduler_running:
        elog = get_logger("economic_scheduler")
        elog.warning("경제 데이터 스케줄러가 이미 실행 중입니다.")
        return False
    
    schedule.every().day.at(settings.SCHEDULE_ECONOMIC_UPDATE_TIME).do(_run_economic_data_update)
    
    # 별도 스레드에서 스케줄러 실행
    economic_data_scheduler_running = True
    economic_data_scheduler_thread = threading.Thread(target=_run_economic_scheduler)
    economic_data_scheduler_thread.daemon = True
    economic_data_scheduler_thread.start()
    
    elog = get_logger("economic_scheduler")
    elog.info(
        "경제 데이터 스케줄러 시작 (KST %s, 추론 후행: %s)",
        settings.SCHEDULE_ECONOMIC_UPDATE_TIME,
        settings.SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE,
    )
    ensure_eod_llm_report_daily_job_scheduled()
    return True

def stop_economic_data_scheduler():
    """경제 데이터 업데이트 스케줄러 중지 함수"""
    global economic_data_scheduler_running, economic_data_scheduler_thread
    
    if not economic_data_scheduler_running:
        elog = get_logger("economic_scheduler")
        elog.warning("경제 데이터 스케줄러가 실행 중이 아닙니다.")
        return False
    
    # 경제 데이터 관련 작업 취소
    economic_jobs = [job for job in schedule.jobs if job.job_func.__name__ == '_run_economic_data_update']
    for job in economic_jobs:
        schedule.cancel_job(job)
    
    economic_data_scheduler_running = False
    if economic_data_scheduler_thread:
        economic_data_scheduler_thread.join(timeout=5)
        economic_data_scheduler_thread = None
    
    elog = get_logger("economic_scheduler")
    elog.info("경제 데이터 업데이트 스케줄러가 중지되었습니다.")
    return True

def run_economic_data_update_now():
    """즉시 경제 데이터 업데이트 실행 함수 (테스트용)"""
    return _run_economic_data_update("즉시실행")


def run_inference_now():
    """경제 갱신 없이 즉시 추론·예측 DB만 갱신 (테스트용)"""
    from app.services.ml_inference_client import trigger_inference

    return trigger_inference()