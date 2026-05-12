"""스케줄·트레이딩 관련 텔레그램 알림 (본문이 길면 분할 전송)."""

from __future__ import annotations

# ─── 모듈 임포트 ───
import json
import traceback
from typing import Any

from alarm.telegram import send_telegram_long_text
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── 헬퍼 함수 ───


def _tg_prefix() -> str:
    """
    텔레그램 메시지 접두사.
    - TELEGRAM_MESSAGE_PREFIX가 있으면 사용
    - 없으면 PROJECT_NAME 기반: [<PROJECT_NAME>]
    """
    try:
        from app.core.config import settings

        v = (settings.TELEGRAM_MESSAGE_PREFIX or "").strip()
        if v:
            return v
        name = (settings.PROJECT_NAME or "").strip() or "Trader-AI"
        return f"[{name}]"
    except Exception:
        return "[Trader-AI]"


def _json_pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _get_usdkrw() -> float | None:
    try:
        from app.services.balance_service import _best_effort_usdkrw
        return _best_effort_usdkrw()
    except Exception:
        return None


def _get_portfolio_returns() -> tuple[float | None, float | None]:
    try:
        from app.services.daily_log_service import _compute_portfolio_snapshot
        return _compute_portfolio_snapshot()
    except Exception:
        return None, None


def _fmt_usd(usd: float, usdkrw: float | None) -> str:
    if usdkrw and usdkrw > 0:
        krw = usd * usdkrw
        return f"${usd:.2f}(₩{krw:,.0f})"
    return f"${usd:.2f}"


def _format_portfolio_returns_section(usdkrw: float | None) -> str:
    holdings_pct, seed_pct = _get_portfolio_returns()
    lines = ["\n━━ 포트폴리오 수익률 ━━"]
    if holdings_pct is not None:
        s = "+" if holdings_pct >= 0 else ""
        lines.append(f"📈 보유종목 기준 수익률: {s}{holdings_pct:.2f}%")
    else:
        lines.append("📈 보유종목 기준 수익률: —")
    if seed_pct is not None:
        s = "+" if seed_pct >= 0 else ""
        lines.append(f"🌱 시드(시작자금) 기준 수익률: {s}{seed_pct:.2f}%")
    else:
        lines.append("🌱 시드(시작자금) 기준 수익률: —")
    if usdkrw and usdkrw > 0:
        lines.append(f"💱 환율: ₩{usdkrw:,.0f}/USD")
    return "\n".join(lines)


# ─── 공개 API ───


def notify_telegram_daily_eod_report(report_text: str, *, ny_date: str) -> bool:
    """미국장 마감 일일 LLM 리포트. 전송 성공 시 True."""
    p = _tg_prefix()
    body = f"{p} 미국장 마감 일일 리포트 (NY {ny_date})\n\n{(report_text or '').strip()}"
    return bool(send_telegram_long_text(body))


def notify_telegram_eod_report_generation_failed(
    exc: BaseException,
    *,
    ny_date: str,
    phase: str = "general",
) -> None:
    """EOD 리포트 생성/전송 실패 알림."""
    # 텔레그램은 "실패 사유" 위주로 짧게. (traceback은 로그로 충분)
    p = _tg_prefix()
    body = "\n".join(
        [
            f"{p} EOD LLM 리포트 실패 (NY {ny_date}, phase={phase})",
            f"사유: {str(exc)}",
        ]
    )
    if not send_telegram_long_text(body):
        logger.debug("텔레그램 미설정 또는 전송 실패(EOD 실패 알림)")


def _format_holdings_section(balance: dict | None, usdkrw: float | None = None) -> str:
    """보유 종목 + 평가손익 섹션 문자열 반환."""
    if not balance:
        return ""
    holdings = balance.get("output1") or []
    if not holdings:
        return "\n━━ 보유 종목 없음 ━━"
    lines = ["\n━━ 보유 종목 ━━"]
    total_pl = 0.0
    total_cost = 0.0
    for h in holdings:
        ticker = h.get("ovrs_pdno", "")
        name = h.get("ovrs_item_name") or ticker
        qty = h.get("ovrs_cblc_qty", "0")
        avg = float(h.get("pchs_avg_pric") or 0)
        now_p = float(h.get("now_pric2") or 0)
        pl_amt = float(h.get("frcr_evlu_pfls_amt") or 0)
        pl_rt = float(h.get("evlu_pfls_rt") or 0)
        try:
            total_cost += avg * float(qty or 0)
        except (ValueError, TypeError):
            pass
        total_pl += pl_amt
        s = "+" if pl_amt >= 0 else ""
        sr = "+" if pl_rt >= 0 else ""
        avg_str = _fmt_usd(avg, usdkrw)
        now_str = _fmt_usd(now_p, usdkrw)
        pl_str = _fmt_usd(abs(pl_amt), usdkrw)
        lines.append(f"  {name}({ticker}) {qty}주 | 매수{avg_str} → 현재{now_str} | {s}{pl_str} ({sr}{pl_rt:.2f}%)")
    s = "+" if total_pl >= 0 else ""
    total_pl_str = _fmt_usd(abs(total_pl), usdkrw)
    if total_cost > 0:
        total_pct = total_pl / total_cost * 100
        sp = "+" if total_pct >= 0 else ""
        lines.append(f"\n📊 총 평가손익: {s}{total_pl_str} ({sp}{total_pct:.2f}%)")
    else:
        lines.append(f"\n📊 총 평가손익: {s}{total_pl_str}")
    return "\n".join(lines)


def notify_telegram_auto_sell_run(summary: dict | None) -> bool:
    """자동 매도 1분 점검 결과 — 잔고·후보 조건·수익률 포함."""
    summary = summary or {}
    kst = summary.get("kst", "")
    ny = summary.get("ny_et", "")
    items = summary.get("items") or []
    candidate_count = int(summary.get("candidate_count") or 0)
    balance = summary.get("balance_snapshot")

    usdkrw = _get_usdkrw()

    ordered = [i for i in items if i.get("outcome") == "order_success"]
    failed_order = [i for i in items if i.get("outcome") == "order_failed"]

    p = _tg_prefix()
    lines = [f"{p} 자동 매도 점검"]
    lines.append(f"⏰ {kst}  (NY: {ny})")

    if candidate_count == 0:
        lines.append("ℹ️ 매도 후보 없음")
    else:
        lines.append(
            f"📊 후보 {candidate_count}개 | 매도성공 {len(ordered)}건 | 실패 {len(failed_order)}건"
        )

    if items:
        lines.append("\n━━ 후보 상세 ━━")
        for it in items:
            outcome = it.get("outcome", "")
            ticker = it.get("ticker", "")
            name = it.get("stock_name") or ticker
            qty = it.get("quantity", "")
            lp = it.get("limit_price")
            pp = it.get("purchase_price")
            pct = it.get("price_change_pct")
            sell_reasons = it.get("sell_reasons") or []
            tech = it.get("tech_details") or []
            sentiment = it.get("sentiment_score")

            lp_str = _fmt_usd(float(lp), usdkrw) if lp is not None else "—"
            if outcome == "order_success":
                st = f"✅ 매도완료 @{lp_str}"
            elif outcome == "order_failed":
                st = f"❌ 매도실패: {it.get('error', '')}"
            else:
                st = f"⚠️ {outcome}"

            price_info = ""
            if pp is not None and lp is not None:
                sign = "+" if (pct or 0) >= 0 else ""
                pct_str = f"{sign}{pct:.1f}%" if pct is not None else ""
                pp_str = _fmt_usd(float(pp), usdkrw)
                price_info = f" | 매수{pp_str}→현재{lp_str} ({pct_str})"

            lines.append(f"\n🔸 {name}({ticker}) {qty}주{price_info}")
            lines.append(f"   {st}")
            for r in sell_reasons:
                lines.append(f"   근거: {r}")
            if tech:
                lines.append(f"   기술지표: {', '.join(str(t) for t in tech)}")
            if sentiment is not None:
                lines.append(f"   감성: {float(sentiment):.3f}")

    lines.append(_format_portfolio_returns_section(usdkrw))

    holdings_text = _format_holdings_section(balance, usdkrw)
    if holdings_text:
        lines.append(holdings_text)

    try:
        from app.core.config import settings as _s
        lines.append(
            f"\n⚙️ 기준: 익절+{_s.SELL_TAKE_PROFIT_PCT}% | 손절{_s.SELL_STOP_LOSS_PCT}% | RSI>{_s.SELL_RSI_OVERBOUGHT} | 감성<{_s.SELL_SENTIMENT_MAX}"
        )
    except Exception:
        pass

    body = "\n".join(lines)
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.warning("자동 매도 텔레그램 전송 실패 또는 미설정(TELEGRAM_*). stock_scheduler.log 확인.")
    return sent


def notify_telegram_auto_buy_run(summary: dict | None, *, label: str | None = None) -> bool:
    """자동 매수 결과 — 잔고·후보 분석·수익률 포함."""
    summary = summary or {}
    kst = summary.get("kst", "")
    items = summary.get("items") or []
    candidate_count = int(summary.get("candidate_count") or 0)
    ordered_count = int(summary.get("ordered_count") or 0)
    status = summary.get("status", "")
    balance = summary.get("balance_snapshot")

    usdkrw = _get_usdkrw()

    ordered = [i for i in items if i.get("outcome") == "order_success"]
    already = [i for i in items if i.get("outcome") == "already_holding"]
    failed = [i for i in items if i.get("outcome") == "order_failed"]

    p = _tg_prefix()
    suffix = f" {label.strip()}" if (label or "").strip() else ""
    lines = [f"{p} 자동 매수 결과{suffix}"]
    lines.append(f"⏰ {kst}")

    if status == "insufficient_balance":
        cash = summary.get("cash_usd")
        cash_str = f"${cash:.2f}" if cash is not None else "알 수 없음"
        lines.append(f"💰 잔고 부족으로 매수 중단 (주문가능 잔고: {cash_str})")
    elif status in ("no_candidates", "balance_error", "balance_exception"):
        lines.append(f"ℹ️ {status}")
    else:
        insuf = [i for i in items if i.get("outcome") == "insufficient_balance"]
        lines.append(
            f"📊 후보 {candidate_count}개 | 매수성공 {ordered_count}건 | 이미보유 {len(already)}개 | 실패 {len(failed)}건"
            + (f" | 잔고부족 {len(insuf)}건" if insuf else "")
        )

    actionable = [i for i in items if i.get("outcome") not in ("already_holding",)]
    if actionable:
        lines.append("\n━━ 매수 상세 ━━")
        for it in actionable:
            outcome = it.get("outcome", "")
            ticker = it.get("ticker", "")
            name = it.get("stock_name") or ticker
            qty = it.get("quantity", "")
            lp = it.get("limit_price")

            lp_str = _fmt_usd(float(lp), usdkrw) if lp is not None else "—"
            if outcome == "order_success":
                lines.append(f"\n✅ {name}({ticker}) {qty}주 @{lp_str}")
            elif outcome == "order_failed":
                lines.append(f"\n❌ {name}({ticker}) 매수실패: {it.get('error', '')}")
                continue
            elif outcome == "insufficient_balance":
                req = it.get("required_usd")
                rem = it.get("remaining_cash_usd")
                req_str = f"${req:.2f}" if req is not None else "—"
                rem_str = f"${rem:.2f}" if rem is not None else "—"
                lines.append(f"\n💰 {name}({ticker}) 잔고부족 — 필요 {req_str} / 남은 잔고 {rem_str}")
                continue
            elif outcome == "price_fetch_failed":
                lines.append(f"\n❌ {name}({ticker}) 현재가 조회 실패: {it.get('error', '')}")
                continue
            elif outcome == "invalid_price":
                lines.append(f"\n❌ {name}({ticker}) 유효하지 않은 현재가")
                continue
            else:
                lines.append(f"\n⚠️ {name}({ticker}) {outcome}")
                continue

            detail_parts = []
            if it.get("accuracy") is not None:
                detail_parts.append(f"모델정확도{float(it['accuracy']):.0f}%")
            if it.get("rise_probability") is not None:
                detail_parts.append(f"상승확률{float(it['rise_probability']):.1f}%")
            if it.get("rsi") is not None:
                detail_parts.append(f"RSI {float(it['rsi']):.1f}")
            if it.get("golden_cross") is not None:
                detail_parts.append("골든크로스" if it["golden_cross"] else "데드크로스")
            if it.get("macd_buy_signal") is not None:
                detail_parts.append("MACD↑" if it["macd_buy_signal"] else "MACD↓")
            if it.get("sentiment_score") is not None:
                detail_parts.append(f"감성{float(it['sentiment_score']):.2f}")
            if it.get("composite_score") is not None:
                detail_parts.append(f"종합점수{float(it['composite_score']):.2f}")
            if detail_parts:
                lines.append(f"   {' | '.join(detail_parts)}")

    if already:
        lines.append(f"\n➖ 이미 보유: {', '.join(i.get('ticker','') for i in already)}")

    lines.append(_format_portfolio_returns_section(usdkrw))

    holdings_text = _format_holdings_section(balance, usdkrw)
    if holdings_text:
        lines.append(holdings_text)

    body = "\n".join(lines)
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.warning("자동 매수 텔레그램 전송 실패 또는 미설정(TELEGRAM_*)")
    return sent


def notify_telegram_trading_job_exception(job_label: str, exc: BaseException) -> None:
    """자동 매수/매도 작업 전체 예외."""
    p = _tg_prefix()
    body = "\n".join(
        [
            f"{p} {job_label} 작업 전체 예외",
            str(exc),
            traceback.format_exc(),
        ]
    )
    if not send_telegram_long_text(body):
        logger.debug("텔레그램 미설정 또는 전송 실패(%s)", job_label)


def notify_telegram_economic_update(result: dict | None, *, source: str) -> bool:
    """경제·주가 일일(또는 수동) 갱신 성공/실패."""
    result = result or {}
    if result.get("success"):
        dr = result.get("date_range") or {}
        payload = {
            "message": result.get("message"),
            "total_records": result.get("total_records"),
            "updated_records": result.get("updated_records"),
            "date_range": dr,
        }
        body = "\n".join(
            [
                f"{_tg_prefix()} 경제·주가 DB 갱신 성공 ({source})",
                _json_pretty(payload),
            ]
        )
    else:
        parts = [
            f"{_tg_prefix()} 경제·주가 DB 갱신 실패 ({source})",
            f"error: {result.get('error', '알 수 없음')}",
        ]
        tb = result.get("traceback")
        if tb:
            parts.extend(["", "traceback:", str(tb)])
        body = "\n".join(parts)

    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(경제 %s)", source)
    return sent


def notify_telegram_inference_success(inf: dict | None, *, source: str) -> bool:
    """추론·DB 갱신 성공 (analysis_records 전체)."""
    inf = inf or {}
    payload = {
        "model_dir": inf.get("model_dir"),
        "prediction_rows": inf.get("prediction_rows"),
        "analysis_rows": inf.get("analysis_rows"),
        "write_db": inf.get("write_db"),
        "analysis_records": inf.get("analysis_records") or [],
    }
    body = "\n".join(
        [
            f"{_tg_prefix()} 추론·DB 갱신 성공 ({source})",
            _json_pretty(payload),
        ]
    )
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(추론 성공 %s)", source)
    return sent


def notify_telegram_inference_failure(exc: BaseException, *, source: str) -> bool:
    """추론·DB 갱신 실패."""
    body = "\n".join(
        [
            f"{_tg_prefix()} 추론·DB 갱신 실패 ({source})",
            str(exc),
            traceback.format_exc(),
        ]
    )
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(추론 실패 %s)", source)
    return sent


def notify_telegram_inference_skipped(
    *,
    source: str,
    reason: str,
    context: dict | None = None,
) -> bool:
    """추론 스킵 알림(할 게 없거나 조건 불충족이어도 결과를 통일성 있게 전송)."""
    payload = {"reason": reason, "context": context or {}}
    body = "\n".join(
        [
            f"{_tg_prefix()} 추론 스킵 ({source})",
            _json_pretty(payload),
        ]
    )
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(추론 스킵 %s)", source)
    return sent


def notify_telegram_sentiment_update(result: dict | None, *, source: str) -> bool:
    """뉴스 감성 분석 결과 전송 (성공·실패 모두)."""
    result = result or {}
    if result.get("error"):
        body = "\n".join(
            [
                f"{_tg_prefix()} 뉴스 감성 분석 실패 ({source})",
                str(result.get("error")),
            ]
        )
    else:
        results = result.get("results") or []
        analyzed = sum(1 for r in results if r.get("average_sentiment_score") is not None)
        no_article = sum(1 for r in results if r.get("message") == "관련 기사 없음")
        body = "\n".join(
            [
                f"{_tg_prefix()} 뉴스 감성 분석 완료 ({source})",
                _json_pretty({
                    "전체_티커수": len(results),
                    "감성점수_저장": analyzed,
                    "기사없음": no_article,
                    "요약": result.get("message"),
                }),
            ]
        )
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(감성 분석 %s)", source)
    return sent


def notify_telegram_sentiment_skipped(
    *,
    source: str,
    reason: str,
    context: dict | None = None,
) -> bool:
    """감성 분석 스킵 알림(이미 적재돼도 결과를 통일성 있게 전송)."""
    payload = {"reason": reason, "context": context or {}}
    body = "\n".join(
        [
            f"{_tg_prefix()} 뉴스 감성 분석 스킵 ({source})",
            _json_pretty(payload),
        ]
    )
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(감성 스킵 %s)", source)
    return sent


def notify_telegram_trading_initialize(result: dict | None, *, source: str = "api") -> bool:
    """
    모의투자 초기화(거래 상태 리셋) 결과를 텔레그램으로 전송한다.

    - DB 삭제(테이블별 ok/deleted/error)
    - 시작자금(seed) 반영 여부 및 best-effort 환율/USD 추정치
    - KIS reset 시도/스킵/실패 사유
    """
    result = result or {}
    kis = result.get("kis_reset") or {}
    db = result.get("db_reset") or {}

    ok = result.get("ok")
    db_ok = result.get("db_ok", db.get("ok"))
    kis_attempted = result.get("kis_attempted", kis.get("attempted"))
    kis_skipped = result.get("kis_skipped", kis.get("skipped"))
    kis_success = result.get("kis_success", kis.get("success"))
    kis_market_hours = result.get("kis_market_hours", kis.get("market_hours"))

    title_status = "성공" if ok else "실패/경고"
    p = _tg_prefix()
    lines: list[str] = [f"{p} 모의투자 초기화 결과 ({title_status}, source={source})"]

    # 요약 라인
    lines.append(
        _json_pretty(
            {
                "ok": ok,
                "db_ok": db_ok,
                "kis": {
                    "attempted": kis_attempted,
                    "skipped": kis_skipped,
                    "success": kis_success,
                    "market_hours": kis_market_hours,
                },
            }
        )
    )

    # DB 삭제 상태
    del_status = (db or {}).get("delete_status") or {}
    if isinstance(del_status, dict) and del_status:
        lines.append("\n━━ DB 삭제 상태 ━━")
        for table, st in del_status.items():
            if not isinstance(st, dict):
                lines.append(f"- {table}: {st}")
                continue
            tok = "✅" if st.get("ok") else "❌"
            deleted = st.get("deleted")
            err = st.get("error")
            extra = []
            if deleted is not None:
                extra.append(f"deleted={deleted}")
            if err:
                extra.append(f"error={err}")
            lines.append(f"- {tok} {table}" + (f" · {', '.join(extra)}" if extra else ""))

    # Seed(시작 자금) 상태
    lines.append("\n━━ Seed(시작자금) ━━")
    lines.append(
        _json_pretty(
            {
                "seed_ok": db.get("seed_ok", db.get("holdings_summary_seeded")),
                "initial_cash_krw": db.get("initial_cash_krw"),
                "usdkrw_best_effort": db.get("usdkrw_best_effort"),
                "usdkrw_source": db.get("usdkrw_source"),
                "initial_cash_usd_best_effort": db.get("initial_cash_usd_best_effort"),
            }
        )
    )

    # KIS reset 상태
    lines.append("\n━━ KIS reset ━━")
    if kis_skipped:
        reason = kis.get("reason") or "skipped"
        lines.append(f"- ⚠️ 장외/조건으로 스킵: {reason}")
    elif kis_attempted and kis_success is False:
        lines.append(f"- ❌ 실패: {kis.get('error') or 'unknown'}")
    elif kis_attempted:
        lines.append("- ✅ 시도/완료")
    else:
        lines.append("- ℹ️ 미시도")

    # 전체 raw 결과(디버깅용)
    lines.append("\n━━ RAW ━━")
    lines.append(_json_pretty(result))

    body = "\n".join(lines)
    sent = bool(send_telegram_long_text(body))
    if not sent:
        logger.debug("텔레그램 미설정 또는 전송 실패(모의투자 초기화 %s)", source)
    return sent
