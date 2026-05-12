"""
한국투자증권 잔고·예약주문·체결·주문 API 라우트.

요청 본문은 Pydantic 모델로 검증하고 `balance_service` 에 위임한다.
"""

# ─── 모듈 임포트 ───
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import pytz

from app.core.config import settings
from app.utils.logger import get_logger
from app.services.balance_service import (
    get_domestic_balance,
    get_overseas_balance,
    overseas_order_resv,
    inquire_psamount,
    get_current_price,
    get_overseas_nccs,
    get_overseas_order_detail,
    get_overseas_order_resv_list,
    get_merged_overseas_filled_orders,
    order_overseas_stock,
    create_conditional_orders,
    reset_mock_investment,
    get_holdings_from_db,
    get_order_fills_from_db,
    get_order_history_from_db,
    sync_holdings_to_db,
    sync_order_fills_to_db,
    get_open_orders_from_db,
    sync_open_orders_to_db,
    reset_trading_state_in_db,
)

logger = get_logger(__name__)
router = APIRouter()

# ─── 엔드포인트 핸들러 ───


@router.get("/", summary="국내주식 잔고 조회")
def read_balance():
    try:
        result = get_domestic_balance()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"잔고 조회 중 오류 발생: {str(e)}")

@router.get("/overseas", summary="해외주식 잔고 조회 (KIS 직접)")
def read_balance_overseas(ovrs_excg_cd: str = Query(default="NASD")):
    """KIS API에서 직접 전 거래소(NASD/NYSE/AMEX) 잔고를 조회한다.

    - 24/7 조회 가능 (장외에도 동작).
    - DB 동기화 오차 없음.
    - DB 폴백은 /balance/overseas/db 사용.
    """
    try:
        from app.services.balance_service import get_all_overseas_balances
        r = get_all_overseas_balances()
        if isinstance(r, dict):
            if "cash_usd_best_effort" in r:
                r["cashUsdBestEffort"] = r.pop("cash_usd_best_effort")
            r["_source"] = "kis_live"
            # holdings_summary에서 initial_cash_usd 조회해서 포함
            try:
                from app.services.balance_service import supabase as _sb
                row = (_sb.table("holdings_summary").select("initial_cash_usd").eq("id", "main").limit(1).execute().data or [{}])[0]
                v = row.get("initial_cash_usd")
                r["initialCashUsd"] = float(v) if v is not None else None
            except Exception:
                r["initialCashUsd"] = None
        return r
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"잔고 조회 중 오류 발생: {str(e)}")


@router.get("/overseas/kis-raw", summary="해외주식 잔고 조회 (KIS 원본 그대로)")
def read_balance_overseas_kis_raw():
    """KIS 조회 결과를 그대로 반환(가공/DB 보강 없음)."""
    try:
        from app.services.balance_service import get_all_overseas_balances

        r = get_all_overseas_balances()
        if isinstance(r, dict):
            r["_source"] = "kis_raw"
        return r
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KIS 원본 잔고 조회 실패: {str(e)}")


@router.get("/overseas/db", summary="해외주식 잔고 조회 (DB 스냅샷)")
def read_balance_overseas_db():
    """Supabase holdings/holdings_summary 기반 스냅샷."""
    try:
        r = get_holdings_from_db()
        if isinstance(r, dict):
            r["_source"] = "db"
        return r
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 잔고 조회 실패: {str(e)}")


@router.get("/cash-usd/kis", summary="KIS 기준 주문가능 외화(USD) 조회")
def read_cash_usd_kis(
    ovrs_excg_cd: str = Query(default="NASD", description="거래소 코드 (NASD/NYSE/AMEX)"),
    item_cd: str = Query(default="AAPL", description="종목 코드 (예: AAPL)"),
    ovrs_ord_unpr: str = Query(default="1", description="주문 단가(USD). 1 같은 작은 값 권장"),
):
    """
    KIS '매수가능금액 조회'를 통해 주문가능 외화(USD)를 조회한다.

    - 해외 잔고 조회(output2)가 현금 필드를 제공하지 않는 경우가 있어, 이 엔드포인트를 truth source로 사용한다.
    """
    try:
        r = inquire_psamount(
            {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "ITEM_CD": item_cd,
                "OVRS_ORD_UNPR": ovrs_ord_unpr,
            }
        )
        out = r.get("output") if isinstance(r, dict) else None
        if not isinstance(out, dict):
            return {"rt_cd": "1", "msg_cd": "BAD_OUTPUT", "msg1": "output 형식이 올바르지 않습니다.", "raw": r}

        def _f(k: str) -> float | None:
            try:
                v = out.get(k)
                if v is None:
                    return None
                return float(str(v).strip() or "0")
            except Exception:
                return None

        # KIS 문서/샘플마다 키가 달라 best-effort로 여러 키를 함께 반환한다.
        candidates = {
            "ord_psbl_frcr_amt": _f("ord_psbl_frcr_amt"),
            "ovrs_ord_psbl_amt": _f("ovrs_ord_psbl_amt"),
            "frcr_ord_psbl_amt1": _f("frcr_ord_psbl_amt1"),
            "echm_af_ord_psbl_amt": _f("echm_af_ord_psbl_amt"),
        }
        best = max([v for v in candidates.values() if isinstance(v, (int, float))], default=0.0)
        return {
            "rt_cd": r.get("rt_cd"),
            "msg_cd": r.get("msg_cd"),
            "msg1": r.get("msg1"),
            "currency": out.get("tr_crcy_cd"),
            "cash_usd_best_effort": best,
            "candidates": candidates,
            "exrt": out.get("exrt"),
            "raw_output": out,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KIS 현금(매수가능) 조회 실패: {str(e)}")



# 해외주식 예약주문 접수 요청 모델
class OrderResvRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD - 나스닥)
    ft_ord_qty: str  # 주문 수량 (예: 1)
    ft_ord_unpr3: str  # 주문 단가 (예: 148.00)
    is_buy: bool = True  # 매수 여부 (True: 매수, False: 매도)
    ord_dvsn: str = "00"  # 주문구분 (00: 지정가, 31: MOO - 미국 매도 예약주문만 가능)

@router.post("/order-resv", summary="해외주식 예약주문 접수")
def order_resv_route(order: OrderResvRequest):
    """
    해외주식 예약주문 접수 API

    미국 예약주문 접수시간
    1) 10:00 ~ 23:20 / 10:00 ~ 22:20 (서머타임 시)
    2) 주문제한 : 16:30 ~ 16:45 경까지 (사유 : 시스템 정산작업시간)
    3) 23:30 정규장으로 주문 전송 (서머타임 시 22:30 정규장 주문 전송)
    4) 미국 거래소 운영시간(한국시간 기준) : 23:30 ~ 06:00 (썸머타임 적용 시 22:30 ~ 05:00)

    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL - 애플 주식)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)
    - **ft_ord_qty**: 주문 수량 (예: 1 - 1주 매수)
    - **ft_ord_unpr3**: 주문 단가 (예: 148.00 - 달러 단위로 소수점 2자리까지)
    - **is_buy**: 매수 여부 (True: 매수, False: 매도) - 거래소에 따라 알맞은 TR_ID가 자동 지정됨
    - **ord_dvsn**: 주문구분 
        - "00": 지정가 (전 거래소 공통)
        - "31": MOO(장개시시장가) - 미국 매도 예약주문만 가능
    
    ### 유의사항
    - 미국 외 거래소(중국/홍콩/일본/베트남)는 매수/매도 구분을 위해 is_buy 값을 사용합니다.
    - 미국 매도 예약주문에서만 MOO(장개시시장가) 주문이 가능합니다.
    - 지정한 시간에 주문이 자동으로 전송됩니다.
    - 예약주문의 유효기간은 당일입니다.

    ### 응답
    - 성공 시: 주문 접수 결과 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        order_data = {
            "CANO": settings.KIS_CANO,  # 계좌번호 (환경변수에서 가져옴)
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌상품코드 (환경변수에서 가져옴)
            "PDNO": order.pdno,
            "OVRS_EXCG_CD": order.ovrs_excg_cd,
            "FT_ORD_QTY": order.ft_ord_qty,
            "FT_ORD_UNPR3": order.ft_ord_unpr3,
            "is_buy": order.is_buy,  # 매수/매도 여부
            "ORD_DVSN": order.ord_dvsn,  # 주문 구분 (지정가/MOO 등)
            "ORD_SVR_DVSN_CD": "0"  # 주문 서버 구분 코드 (기본값)
        }
        result = overseas_order_resv(order_data)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "주문 접수 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예약주문 접수 중 오류 발생: {str(e)}")
    
@router.get("/inquire-psamount", summary="해외주식 매수가능금액 조회")
def inquire_psamount_route(
    ovrs_excg_cd: str,
    item_cd: str,
    ovrs_ord_unpr: str
):
    """
    해외주식 매수가능금액 조회 API

    ### 입력값 설명
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)
    - **item_cd**: 종목 코드 (예: AAPL - 애플 주식)
    - **ovrs_ord_unpr**: 주문 단가 (예: 148.00 - 달러 단위로 소수점 2자리까지)

    ### 응답
    - 성공 시: 매수가능 금액 및 수량 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        params = {
            "CANO": settings.KIS_CANO,  # 계좌번호 (환경변수에서 가져옴)
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌상품코드 (환경변수에서 가져옴)
            "OVRS_EXCG_CD": ovrs_excg_cd,
            "ITEM_CD": item_cd,
            "OVRS_ORD_UNPR": ovrs_ord_unpr
        }
        result = inquire_psamount(params)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "조회 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"매수가능금액 조회 중 오류 발생: {str(e)}")
    
@router.get("/quotations/price", summary="해외주식 현재체결가 조회")
def get_current_price_route(
    excd: str,
    symb: str
):
    """
    해외주식 현재체결가 조회 API

    ### 입력값 설명
    - **excd**: 거래소 코드 (예: NAS - 나스닥, NYS - 뉴욕증권거래소)
    - **symb**: 종목 코드 (예: TSLA - 테슬라 주식)

    ### 응답
    - 성공 시: 현재 체결가 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        params = {
            "EXCD": excd,
            "SYMB": symb
        }
        result = get_current_price(params)

        if result.get("rt_cd") != "0":
            raise HTTPException(status_code=400, detail=result.get("msg1", "조회 실패"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"현재체결가 조회 중 오류 발생: {str(e)}")

@router.get("/order-fills", summary="해외주식 최근 체결 내역 (DB)")
def read_order_fills(days: int = Query(30, ge=1, le=365, description="조회 기간(일)")):
    """Supabase order_fills 테이블에서 체결 내역 반환."""
    try:
        rows = get_order_fills_from_db(days=days)
        return {"rt_cd": "0", "output": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"체결 내역 조회 중 오류 발생: {str(e)}")


@router.get("/order-history", summary="매수/매도 주문 이력 (DB)")
def read_order_history():
    """Supabase order_history 테이블에서 주문 이력 반환."""
    try:
        rows = get_order_history_from_db()
        return {"rt_cd": "0", "items": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주문 이력 조회 중 오류 발생: {str(e)}")


@router.get("/nccs", summary="해외주식 미체결내역 조회 (모의투자 환경에서는 지원되지 않습니다.)")
def get_overseas_nccs_route(
    ovrs_excg_cd: str = Query(..., description="거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)"),
    sort_sqn: str = Query("DS", description="정렬순서 (DS: 정순, 그외: 역순)")
):
    """
    해외주식 미체결내역 조회 API
    """
    try:
        # 프론트에 보이는 값은 항상 DB 기반: exchange/sort 파라미터는 호환용으로만 받음
        rows = get_open_orders_from_db()
        return {"rt_cd": "0", "output": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"미체결내역 조회 중 오류 발생: {str(e)}")

@router.get("/order-resv-list", summary="해외주식 예약주문 조회 (모의투자 환경에서는 지원되지 않습니다.)")
def get_overseas_order_resv_list_route(
    ovrs_excg_cd: str = Query(None, description="거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕증권거래소)"),
    inqr_strt_dt: str = Query(..., description="조회 시작일자 (YYYYMMDD)"),
    inqr_end_dt: str = Query(..., description="조회 종료일자 (YYYYMMDD)"),
    inqr_dvsn_cd: str = Query("00", description="조회구분코드 (00: 전체, 01: 일반해외주식, 02: 미니스탁)"),
    prdt_type_cd: str = Query("", description="상품유형코드 (공백: 전체, 512: 미국 나스닥, 515: 일본, 등)")
):
    """
    해외주식 예약주문 조회 API

    ### 입력값 설명
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥, NYSE - 뉴욕)
    - **inqr_strt_dt**: 조회 시작일자 (YYYYMMDD 형식)
    - **inqr_end_dt**: 조회 종료일자 (YYYYMMDD 형식)
    - **inqr_dvsn_cd**: 조회구분코드 (00: 전체, 01: 일반해외주식, 02: 미니스탁)
    - **prdt_type_cd**: 상품유형코드 (공백: 전체조회)
    
    ### 응답
    - 성공 시: 예약주문 내역 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    
    ※ 모의투자 환경에서는 이 API가 지원되지 않습니다.
    """
    try:
        # 날짜 형식 검증
        from datetime import datetime
        try:
            start_date = datetime.strptime(inqr_strt_dt, "%Y%m%d")
            end_date = datetime.strptime(inqr_end_dt, "%Y%m%d")
            
            # 종료일이 시작일보다 이전인지 확인
            if end_date < start_date:
                raise HTTPException(status_code=400, detail="종료일은 시작일 이후여야 합니다.")
        except ValueError:
            raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다. YYYYMMDD 형식으로 입력하세요.")
        
        # 파라미터 설정
        params = {
            "CANO": settings.KIS_CANO,
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
            "INQR_STRT_DT": inqr_strt_dt,
            "INQR_END_DT": inqr_end_dt,
            "INQR_DVSN_CD": inqr_dvsn_cd,
            "PRDT_TYPE_CD": prdt_type_cd,
            "OVRS_EXCG_CD": ovrs_excg_cd if ovrs_excg_cd else "",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": ""
        }
        
        from app.services.balance_service import get_overseas_order_resv_list
        result = get_overseas_order_resv_list(params)
        
        # 모의투자 환경에서는 안내 메시지 반환
        if result.get("msg_cd") == "MOCK_UNSUPPORTED":
            return result
        
        if result.get("rt_cd") != "0":
            status_code = 400 if result.get("rt_cd") == "1" else 500
            raise HTTPException(status_code=status_code, detail=result.get("msg1", "예약주문 조회 실패"))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예약주문 조회 중 오류 발생: {str(e)}")

# 해외주식 주문 요청 모델
class OrderOverseasRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD - 나스닥)
    ord_qty: str  # 주문 수량 (예: 1)
    ovrs_ord_unpr: str  # 주문 단가 (예: 148.00)
    is_buy: bool = True  # 매수 여부 (True: 매수, False: 매도)
    ord_dvsn: str = "00"  # 주문구분 (00: 지정가)

@router.post("/order-overseas", summary="해외주식 매수/매도 주문")
def order_overseas_stock_route(request: OrderOverseasRequest):
    """
    해외주식 매수/매도 주문 API
    
    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL - 애플)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD - 나스닥)
    - **ord_qty**: 주문 수량 (예: 1)
    - **ovrs_ord_unpr**: 주문 단가 (예: 180.00)
    - **is_buy**: 매수 여부 (True: 매수, False: 매도)
    - **ord_dvsn**: 주문구분 (00: 지정가, 그 외 거래소별 문서 참조)
    
    ### 응답
    - 성공 시: 주문 접수 결과 반환
    - 실패 시: 오류 메시지와 함께 HTTP 상태 코드 반환
    """
    try:
        # 주문 데이터 준비
        order_data = {
            "CANO": settings.KIS_CANO,  # 계좌번호 앞 8자리
            "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,  # 계좌번호 뒤 2자리
            "PDNO": request.pdno,  # 종목코드
            "OVRS_EXCG_CD": request.ovrs_excg_cd,  # 해외거래소코드
            "ORD_QTY": request.ord_qty,  # 주문수량
            "OVRS_ORD_UNPR": request.ovrs_ord_unpr,  # 주문단가
            "is_buy": request.is_buy,  # 매수 여부
            "ORD_DVSN": request.ord_dvsn  # 주문구분
        }
        
        # 서비스 함수 호출
        result = order_overseas_stock(order_data)
        
        # 주문 이력 저장(성공/실패 무관하게 남겨야 대시보드/관리자가 상태를 파악 가능)
        try:
            from datetime import datetime
            import pytz
            from app.services.daily_log_service import save_order

            now_ny = datetime.now(pytz.timezone("America/New_York"))
            side = "buy" if bool(request.is_buy) else "sell"
            msg1 = result.get("msg1", "") if isinstance(result, dict) else ""
            save_order(
                side=side,
                ticker=request.pdno,
                stock_name=None,
                exchange_code=request.ovrs_excg_cd,
                quantity=int(float(request.ord_qty)) if request.ord_qty else None,
                limit_price=float(request.ovrs_ord_unpr) if request.ovrs_ord_unpr else None,
                order_type=str(request.ord_dvsn or ""),
                rt_cd=str(result.get("rt_cd")) if isinstance(result, dict) else None,
                api_message=msg1,
                success=bool(isinstance(result, dict) and result.get("rt_cd") == "0"),
                source="manual_api",
                payload={"order_request": order_data, "order_result": result},
                ny_trading_date=now_ny.strftime("%Y-%m-%d"),
            )
        except Exception:
            logger.warning("order_history 저장 실패(무시)", exc_info=True)

        # 결과 확인
        if result.get("rt_cd") != "0":
            error_msg = result.get("msg1", "주문 처리 중 오류가 발생했습니다")
            raise HTTPException(status_code=400, detail=error_msg)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"해외주식 주문 처리 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"주문 처리 중 오류가 발생했습니다: {str(e)}")

@router.post("/sync", summary="KIS → DB 즉시 동기화")
def sync_from_kis():
    """잔고 및 체결 내역을 KIS에서 조회해 Supabase에 즉시 저장합니다."""
    holdings_ok = sync_holdings_to_db()
    fills_ok = sync_order_fills_to_db()
    open_ok = sync_open_orders_to_db()
    return {"holdings": holdings_ok, "order_fills": fills_ok, "open_orders": open_ok}


@router.post("/reset", summary="모의투자 리셋 (전체 보유 종목 전량 매도)")
def reset_mock_investment_route():
    """
    모의투자 리셋 API

    전체 보유 종목을 현재가 기준으로 전량 매도합니다.
    리셋 후 스케줄러는 그대로 유지되며, 다음 장 오픈 시 정상 매수/매도가 재개됩니다.

    ### 응답
    - **sold**: 매도 성공한 종목 리스트 (ticker, quantity, price, exchange_code)
    - **failed**: 매도 실패한 종목 리스트 (ticker, error)
    - **skipped**: 수량 0 등으로 건너뛴 종목 리스트
    - **success**: 전체 성공 여부

    ※ 모의투자 환경에서만 사용하는 것을 권장합니다.
    """
    try:
        result = reset_mock_investment()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리셋 중 오류 발생: {str(e)}")


@router.post("/initialize", summary="모의투자 초기화(거래 상태 초기화 + 시작 자금 세팅)")
def initialize_mock_trading():
    """
    '처음부터 다시 시작' 용도.
    - KIS 전량 매도(가능하면) 시도
    - Supabase 거래 상태 테이블(holdings/order_fills/open_orders 등) 초기화
    - 시작 자금(기본 5억 원)을 holdings_summary에 시드(best-effort USD로 환산)

    경제/추론/감성 데이터는 유지한다.
    """
    try:
        # 초기화 중 매도 스케줄러가 동시에 DB를 갱신/주문하지 않도록 일시 중지 후 재시작한다.
        scheduler_before = None
        scheduler_stop = {"attempted": False, "stopped": None, "error": None}
        scheduler_start = {"attempted": False, "started": None, "error": None}
        try:
            from app.utils.scheduler import get_scheduler_status, start_sell_scheduler, stop_sell_scheduler

            scheduler_before = get_scheduler_status()
            scheduler_stop["attempted"] = True
            # stop_sell_scheduler(): 실행 중이면 True, 이미 중지면 False
            scheduler_stop["stopped"] = bool(stop_sell_scheduler())
        except Exception as se:
            scheduler_stop["attempted"] = True
            scheduler_stop["stopped"] = False
            scheduler_stop["error"] = str(se)
            logger.warning("초기화 전 매도 스케줄러 중지 실패(계속 진행): %s", se)

        # 장외에는 KIS 호출이 제한/실패할 수 있어, 장중일 때만 전량매도 reset을 시도한다.
        # 중요: 장중 판정은 스케줄러와 반드시 동일해야 한다(프론트/텔레그램/스케줄과 불일치 방지).
        ny = pytz.timezone("America/New_York")
        now_ny = datetime.now(ny)
        from app.utils.scheduler import StockScheduler

        is_market_hours, open_dt, close_dt = StockScheduler._calc_market_window(now_ny)
        is_weekday = 0 <= now_ny.weekday() <= 4

        kis_reset = {"attempted": False, "market_hours": is_market_hours, "success": None}
        if is_market_hours:
            kis_reset["attempted"] = True
            try:
                # reset_mock_investment()는 {success, sold, failed, skipped ...}만 반환한다.
                # initialize 응답에서 '실행 여부/장중 여부'를 안정적으로 표시하기 위해 메타 필드를 보강한다.
                # 모의투자에서는 KIS 제약으로 전량매도가 끝까지 안 되는 케이스가 잦아,
                # 초기화 UX를 위해 최대 시도 시간을 더 짧게 잡는다.
                _r = reset_mock_investment(max_total_sec=60 if settings.KIS_USE_MOCK else 180)
                kis_reset = {
                    "attempted": True,
                    "market_hours": True,
                    **(_r if isinstance(_r, dict) else {"success": False, "error": "KIS reset 반환 형식이 올바르지 않습니다."}),
                }
                # 프론트/텔레그램/로그 편의용: 카운트 필드가 없거나 None이면 보강
                try:
                    kis_reset.setdefault("sold_count", len(kis_reset.get("sold") or []))
                    kis_reset.setdefault("failed_count", len(kis_reset.get("failed") or []))
                    kis_reset.setdefault("skipped_count", len(kis_reset.get("skipped") or []))
                    if kis_reset.get("remaining_count") is None:
                        kis_reset["remaining_count"] = len(kis_reset.get("remaining_holdings") or [])
                except Exception:
                    pass
            except Exception as e:
                kis_reset = {"attempted": True, "market_hours": True, "success": False, "error": f"KIS reset 실패: {str(e)}"}

            # 장중 초기화의 목표는 KIS 잔고까지 0으로 만드는 것.
            # 따라서 장중에는 KIS 잔고가 0으로 정착(settled=True)된 경우에만 DB 초기화를 진행한다.
            if kis_reset.get("settled") is not True:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "장중 초기화 실패: KIS 잔고가 0으로 정착되지 않았습니다. (보유 종목이 남아있어 초기화를 완료할 수 없음)",
                        "kis_reset": kis_reset,
                    },
                )
        else:
            kis_reset.update(
                {
                    "attempted": False,
                    "market_hours": False,
                    "success": True,
                    "skipped": True,
                    "reason": "장외(미국 정규장 외)에는 KIS 주문/현재가 호출이 실패할 수 있어 reset을 스킵했습니다.",
                    "now_ny": now_ny.isoformat(),
                    "open_ny": open_dt.isoformat(),
                    "close_ny": close_dt.isoformat(),
                    "is_weekday": is_weekday,
                }
            )
            # 장외: KIS reset 스킵, DB 초기화만 수행

        db_reset = reset_trading_state_in_db(
            wipe_trade_logs=True,
        )
        result = {
            "ok": bool(db_reset.get("ok") and (kis_reset.get("success") is not False)),
            "db_ok": bool(db_reset.get("ok")),
            "kis_attempted": bool(kis_reset.get("attempted")),
            "kis_skipped": bool(kis_reset.get("skipped")),
            "kis_success": kis_reset.get("success"),
            "kis_market_hours": kis_reset.get("market_hours"),
            "kis_reset": kis_reset,
            "db_reset": db_reset,
            "scheduler_before": scheduler_before,
            "scheduler_stop": scheduler_stop,
            "scheduler_start": scheduler_start,
        }

        # 초기화 직후 KIS→DB 재동기화:
        # - 장중: KIS 잔고 0 정착을 선행 보장했으므로, 동기화는 "보유 0"을 DB에 확정하기 위한 절차.
        # - 장외: DB 초기화만 수행하므로 동기화는 시도하지 않는다(KIS 호출 실패 가능).
        post_sync = {"attempted": False, "holdings": None, "order_fills": None, "open_orders": None, "error": None}
        try:
            if (
                bool(kis_reset.get("attempted"))
                and bool(kis_reset.get("market_hours"))
                and (kis_reset.get("settled") is True)
            ):
                post_sync["attempted"] = True
                from app.services.balance_service import (
                    sync_holdings_to_db,
                    sync_order_fills_to_db,
                    sync_open_orders_to_db,
                )

                post_sync["holdings"] = bool(sync_holdings_to_db())
                post_sync["order_fills"] = bool(sync_order_fills_to_db())
                post_sync["open_orders"] = bool(sync_open_orders_to_db())
        except Exception as pse:
            post_sync["attempted"] = True
            post_sync["error"] = str(pse)
            logger.warning("초기화 직후 KIS→DB 재동기화 실패(무시): %s", pse)
        result["post_sync"] = post_sync

        # 초기화 후 매도 스케줄러 재시작(항상 start 시도)
        try:
            from app.utils.scheduler import start_sell_scheduler, stop_sell_scheduler

            scheduler_start["attempted"] = True
            started = start_sell_scheduler()
            # 이미 running 이면 False → stop 후 한 번 더 start 해서 강제 재시작 시도
            if not started:
                try:
                    stop_sell_scheduler()
                except Exception:
                    pass
                started = start_sell_scheduler()
            scheduler_start["started"] = bool(started)
        except Exception as se2:
            scheduler_start["attempted"] = True
            scheduler_start["started"] = False
            scheduler_start["error"] = str(se2)
            logger.warning("초기화 후 매도 스케줄러 시작 실패(무시): %s", se2)

        # 텔레그램 알림(best-effort): 전송 실패로 API 결과가 바뀌지 않도록 한다.
        try:
            from alarm.notify import notify_telegram_trading_initialize

            telegram_sent = bool(notify_telegram_trading_initialize(result, source="api"))
            result["telegram_sent"] = telegram_sent
        except Exception as e:
            # 텔레그램 미설정/네트워크 오류 등은 초기화 자체를 실패시키지 않는다.
            logger.warning("초기화 텔레그램 전송 실패(무시): %s", e)
            result["telegram_sent"] = False
            result["telegram_error"] = str(e)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"초기화 중 오류 발생: {str(e)}")


@router.post("/initialize-db-only", summary="DB만 초기화(거래 상태 + 시작 자금). KIS는 건드리지 않음")
def initialize_db_only():
    """
    KIS(모의투자) 초기화를 한투 사이트에서 수행하는 경우를 위한 모드.
    - KIS 전량매도/취소 등을 시도하지 않는다.
    - Supabase 거래 상태 테이블(holdings/order_fills/open_orders 등) + 매매 로그를 초기화
    - 시작 자금(기본 5억 원)을 holdings_summary에 시드
    """
    try:
        scheduler_before = None
        scheduler_stop = {"attempted": False, "stopped": None, "error": None}
        scheduler_start = {"attempted": False, "started": None, "error": None}
        try:
            from app.utils.scheduler import get_scheduler_status, start_sell_scheduler, stop_sell_scheduler

            scheduler_before = get_scheduler_status()
            scheduler_stop["attempted"] = True
            scheduler_stop["stopped"] = bool(stop_sell_scheduler())
        except Exception as se:
            scheduler_stop["attempted"] = True
            scheduler_stop["stopped"] = False
            scheduler_stop["error"] = str(se)

        db_reset = reset_trading_state_in_db(
            wipe_trade_logs=True,
        )

        # KIS를 건드리지 않으므로, 즉시 KIS→DB 동기화는 "진실(KIS)이 다시 채워지는" 효과가 있어 수행하지 않음.
        result = {
            "ok": bool(db_reset.get("ok")),
            "mode": "db_only",
            "db_ok": bool(db_reset.get("ok")),
            "db_reset": db_reset,
            "scheduler_before": scheduler_before,
            "scheduler_stop": scheduler_stop,
            "scheduler_start": scheduler_start,
        }

        # 초기화 후 매도 스케줄러 재시작(항상 start 시도)
        try:
            from app.utils.scheduler import start_sell_scheduler, stop_sell_scheduler

            scheduler_start["attempted"] = True
            started = start_sell_scheduler()
            if not started:
                try:
                    stop_sell_scheduler()
                except Exception:
                    pass
                started = start_sell_scheduler()
            scheduler_start["started"] = bool(started)
        except Exception as se2:
            scheduler_start["attempted"] = True
            scheduler_start["started"] = False
            scheduler_start["error"] = str(se2)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB-only 초기화 중 오류 발생: {str(e)}")


# 조건부 주문 요청 모델
class ConditionalOrderRequest(BaseModel):
    pdno: str  # 종목 코드 (예: AAPL)
    ovrs_excg_cd: str  # 거래소 코드 (예: NASD)
    base_price: float  # 기준 가격
    stop_loss_percent: Optional[float] = None  # 손절매 퍼센트 (예: -5.0)
    take_profit_percent: Optional[float] = None  # 이익실현 퍼센트 (예: 5.0)
    quantity: str  # 주문 수량

@router.post("/conditional-order", summary="조건부 주문 설정")
def conditional_order_route(request: ConditionalOrderRequest):
    """
    특정 가격에 도달했을 때 자동으로 실행되는 조건부 주문 설정
    
    ### 입력값 설명
    - **pdno**: 종목 코드 (예: AAPL)
    - **ovrs_excg_cd**: 거래소 코드 (예: NASD)
    - **base_price**: 기준 가격 (지정하지 않으면 보유 주식의 매수 가격으로 설정됨)
    - **stop_loss_percent**: 손절매 퍼센트 (예: -5.0)
    - **take_profit_percent**: 이익실현 퍼센트 (예: 5.0)
    - **quantity**: 주문 수량
    
    ### 예시
    - base_price가 100달러이고 stop_loss_percent가 -5.0이면, 주가가 95달러에 도달했을 때 매도 주문 실행
    - base_price가 100달러이고 take_profit_percent가 5.0이면, 주가가 105달러에 도달했을 때 매도 주문 실행
    """
    try:
        # 요청 데이터 준비
        params = {
            "pdno": request.pdno,
            "ovrs_excg_cd": request.ovrs_excg_cd,
            "base_price": request.base_price if request.base_price else None,
            "stop_loss_percent": request.stop_loss_percent if request.stop_loss_percent is not None else -5.0,
            "take_profit_percent": request.take_profit_percent if request.take_profit_percent is not None else 5.0,
            "quantity": request.quantity
        }
        
        # 조건부 주문 실행
        result = create_conditional_orders(params)
        
        # 결과 확인
        if result.get("rt_cd") != "0":
            error_msg = result.get("msg1", "조건부 주문 설정 중 오류가 발생했습니다")
            raise HTTPException(status_code=400, detail=error_msg)
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"조건부 주문 처리 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"조건부 주문 처리 중 오류가 발생했습니다: {str(e)}")
