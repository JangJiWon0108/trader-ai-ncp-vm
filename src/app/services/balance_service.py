"""
한국투자증권(KIS) REST API 연동: 토큰·잔고·주문·예약·체결 조회 등.

`app.api.routes.balance` 및 스케줄러에서 호출된다. 토큰은 메모리·Supabase 와
1분당 갱신 제한을 함께 사용한다.
"""

# ─── 모듈 임포트 ───
import json
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

import pytz
import requests
from requests import RequestException

from app.core.config import settings
from app.db.supabase import supabase
from app.services.auth_service import parse_expiration_date
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 외부 API(특히 KIS/알파밴티지 등) 호출이 무한 대기하지 않도록 기본 타임아웃을 둔다.
# 기존 로직(응답 파싱/에러 처리)은 유지하고, "멈춤"만 방지한다.
_HTTP_TIMEOUT = (5.0, 30.0)  # (connect, read) seconds

# ─── 상수 정의 (토큰 캐시) ───

_token_cache = {
    "access_token": None,
    "expires_at": None
}
_last_refresh_time = 0  # 마지막 토큰 갱신 시간
_refresh_lock = Lock()

# ─── 공개 API ───


def get_access_token():
    """한국투자증권 API 접근 토큰 발급 또는 캐시된 토큰 반환"""
    global _token_cache, _last_refresh_time
    
    # 현재 시간
    now = datetime.now(pytz.UTC)
    
    # 메모리에 캐시된 토큰이 있고 유효하면 그것을 사용
    if _token_cache["access_token"] and _token_cache["expires_at"] and now < _token_cache["expires_at"]:
        logger.info("메모리에 캐시된 토큰 사용")
        return _token_cache["access_token"]
    
    # 1분 제한 체크 및 락 획득
    current_time = time.time()
    if current_time - _last_refresh_time < 60:
        time_to_wait = 60 - (current_time - _last_refresh_time)
        logger.info(f"1분 제한으로 {time_to_wait:.1f}초 대기")
        time.sleep(time_to_wait)
    
    with _refresh_lock:  # 동시성 방지
        # 락 획득 후 다시 캐시 확인
        if _token_cache["access_token"] and _token_cache["expires_at"] and now < _token_cache["expires_at"]:
            logger.info("락 내에서 캐시된 토큰 사용")
            return _token_cache["access_token"]
        
        try:
            # 테이블에서 토큰 레코드 조회
            response = supabase.table("access_tokens").select("*").order("created_at", desc=True).limit(1).execute()
            
            if response.data:
                token_data = response.data[0]
                
                # 이 부분을 수정 - auth_service의 parse_expiration_date 함수 사용
                expiration_time = parse_expiration_date(token_data["expiration_time"])
                
                if now < expiration_time:  # 토큰이 아직 유효한 경우
                    logger.info(f"기존 토큰 사용 - 만료까지 남은 시간: {(expiration_time - now)}")
                    _token_cache["access_token"] = token_data["access_token"]
                    _token_cache["expires_at"] = expiration_time
                    _last_refresh_time = current_time
                    return token_data["access_token"]
                
                logger.info("토큰 만료됨, 갱신 필요")
                # 토큰이 만료된 경우 갱신
                token = refresh_token_with_retry(token_data["id"])
                _token_cache["access_token"] = token
                _token_cache["expires_at"] = now + timedelta(days=1)
                _last_refresh_time = current_time
                return token
            else:
                logger.info("토큰 레코드 없음, 새로 생성")
                token = refresh_token_with_retry()
                _token_cache["access_token"] = token
                _token_cache["expires_at"] = now + timedelta(days=1)
                _last_refresh_time = current_time
                return token
                
        except Exception as e:
            logger.info(f"토큰 조회 오류: {str(e)}")
            if _token_cache["access_token"]:
                logger.info("DB 조회 오류 - 메모리에 캐시된 토큰 사용")
                return _token_cache["access_token"]
            raise Exception(f"토큰 발급 실패: {str(e)}")

def refresh_token_with_retry(record_id=None, max_retries=3):
    """토큰 갱신을 재시도하며 처리"""
    for attempt in range(max_retries):
        try:
            url = f"{settings.kis_base_url}/oauth2/tokenP"
            data = {
                "grant_type": "client_credentials",
                "appkey": settings.KIS_APPKEY,
                "appsecret": settings.KIS_APPSECRET
            }
            
            response = requests.post(url, json=data, timeout=_HTTP_TIMEOUT)
            response_data = response.json() if response.text else {}
            
            if 'access_token' not in response_data:
                raise Exception(f"토큰 발급 실패: {response_data}")
            
            access_token = response_data["access_token"]
            expires_in = response_data.get("expires_in", 86400)  # 기본값 24시간(초)
            now = datetime.now(pytz.UTC)
            expiration_time = now + timedelta(seconds=expires_in)
            
            token_data = {
                "access_token": access_token,
                "expiration_time": expiration_time.isoformat(),
                "is_active": True
            }
            
            # 레코드 ID가 있으면 업데이트, 없으면 새로 생성
            if record_id:
                supabase.table("access_tokens").update(token_data).eq("id", record_id).execute()
                logger.info("토큰 업데이트 완료")
            else:
                supabase.table("access_tokens").insert(token_data).execute()
                logger.info("새 토큰 레코드 생성 완료")
            
            return access_token
            
        except Exception as e:
            logger.info(f"토큰 갱신 오류 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if "EGW00133" in str(e) and attempt < max_retries - 1:
                logger.info("1분 제한 에러 발생, 61초 대기 후 재시도")
                time.sleep(61)  # 1분 이상 대기
            else:
                raise

def get_domestic_balance():
    """국내주식 잔고 조회"""
    # 토큰 가져오기
    access_token = get_access_token()
    
    url = f"{settings.kis_base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
    tr_id = "TTTC8434R" if not settings.KIS_USE_MOCK else "VTTC8434R"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.KIS_APPKEY,
        "appsecret": settings.KIS_APPSECRET,
        "tr_id": tr_id,
    }
    
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "00",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            result = response.json()
            
            # API 응답에 오류가 있고, 재시도 가능한 경우
            if 'rt_cd' in result and result['rt_cd'] != '0' and attempt < max_retries - 1:
                logger.info(f"API 오류: {result['msg_cd']} - {result.get('msg1', '알 수 없는 오류')}. 토큰 갱신 후 재시도...")
                # 토큰 강제 갱신 후 재시도
                access_token = get_access_token()
                headers["authorization"] = f"Bearer {access_token}"
                time.sleep(1)  # 재시도 전 1초 대기
                continue
            
            return result
            
        except Exception as e:
            logger.info(f"잔고 조회 중 오류 발생 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 재시도 전 1초 대기
            else:
                raise

def get_overseas_balance(ovrs_excg_cd="NASD"):
    """해외주식 잔고 조회
    
    Args:
        ovrs_excg_cd (str, optional): 거래소 코드. Defaults to "NASD".
            NASD: 나스닥, NYSE: 뉴욕, AMEX: 아멕스
    """
    # 토큰 가져오기
    access_token = get_access_token()
    
    url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-balance"
    
    tr_id = "TTTS3012R" if not settings.KIS_USE_MOCK else "VTTS3012R"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": settings.KIS_APPKEY,
        "appsecret": settings.KIS_APPSECRET,
        "tr_id": tr_id,
    }
    
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "OVRS_EXCG_CD": ovrs_excg_cd,  # 매개변수로 받은 거래소 코드 사용
        "TR_CRCY_CD": "USD",     # 통화코드 USD
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": ""
    }
    
    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
            result = response.json()
            
            # API 응답에 오류가 있고, 재시도 가능한 경우
            if 'rt_cd' in result and result['rt_cd'] != '0' and attempt < max_retries - 1:
                logger.info(f"API 오류: {result['msg_cd']} - {result.get('msg1', '알 수 없는 오류')}. 토큰 갱신 후 재시도...")
                # 토큰 강제 갱신 후 재시도
                access_token = get_access_token()
                headers["authorization"] = f"Bearer {access_token}"
                time.sleep(1)
                continue
            
            return result
            
        except Exception as e:
            logger.info(f"잔고 조회 중 오류 발생 (시도 {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(1)  # 재시도 전 1초 대기
            else:
                raise

def get_all_overseas_balances():
    """모든 거래소의 해외주식 잔고 조회"""
    # 주요 거래소 목록
    exchanges = ["NASD", "NYSE", "AMEX"]
    all_holdings = []
    output2_best: dict = {}
    cash_usd_best = 0.0
    
    for exchange in exchanges:
        try:
            result = get_overseas_balance(exchange)
            
            if result.get("rt_cd") == "0" and "output1" in result:
                holdings = result.get("output1", [])
                if holdings:
                    all_holdings.extend(holdings)
                # output2(예수금/주문가능외화 등) best-effort 수집
                o2 = result.get("output2") or {}
                if isinstance(o2, dict) and o2:
                    output2_best = o2
                    for k in ("ovrs_ord_psbl_amt", "ord_psbl_frcr_amt"):
                        try:
                            v = float(str(o2.get(k) or "0") or "0")
                        except Exception:
                            v = 0.0
                        if v > cash_usd_best:
                            cash_usd_best = v
            else:
                logger.info(f"{exchange} 거래소 잔고 조회 실패: {result.get('msg1', '알 수 없는 오류')}")
                
            # API 요청 간 지연 (KIS 초당 1건 제한)
            time.sleep(1.1)
            
        except Exception as e:
            logger.info(f"{exchange} 거래소 잔고 조회 중 오류: {str(e)}")
    
    # 동일 종목이 NASD/NYSE/AMEX 각 조회에 중복 포함되는 경우 제거 (첫 조회 순서 유지)
    seen_pdno = set()
    deduped_holdings = []
    for h in all_holdings:
        pdno = (h.get("ovrs_pdno") or "").strip()
        if pdno:
            if pdno in seen_pdno:
                continue
            seen_pdno.add(pdno)
        deduped_holdings.append(h)

    # output2에 현금 필드가 없는 경우(모의투자 등) psamount로 보완
    if cash_usd_best <= 0:
        try:
            ps_cash, _ = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd="NASD")
            if ps_cash and ps_cash > 0:
                cash_usd_best = ps_cash
        except Exception:
            pass

    # 통합된 잔고 정보 반환
    msg = "모든 거래소 잔고 조회 완료" if deduped_holdings else "보유 종목이 없습니다."
    return {
        "rt_cd": "0",
        "msg_cd": "00000",
        "msg1": msg,
        "output1": deduped_holdings,
        "output2": output2_best,
        "cash_usd_best_effort": cash_usd_best,
    }

# 추가: 해외주식 예약주문 접수
def overseas_order_resv(order_data):
    """해외주식 예약주문 접수"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order-resv"
        
        is_mock = settings.KIS_USE_MOCK
        
        # 매수/매도 여부 및 거래소에 따라 TR_ID 결정
        is_buy = order_data.get("is_buy", True)
        ovrs_excg_cd = order_data.get("OVRS_EXCG_CD", "")
        
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"]:  # 미국 주식
            if is_buy:
                tr_id = "VTTT3014U" if is_mock else "TTTT3014U"  # 미국 매수 예약
            else:
                tr_id = "VTTT3016U" if is_mock else "TTTT3016U"  # 미국 매도 예약
        else:  # 기타 거래소
            tr_id = "VTTS3013U" if is_mock else "TTTS3013U"  # 중국/홍콩/일본/베트남 예약
            
            # 중국/홍콩/일본/베트남의 경우 매수/매도 구분 코드 추가
            if not is_buy:
                order_data["SLL_BUY_DVSN_CD"] = "01"  # 매도
            else:
                order_data["SLL_BUY_DVSN_CD"] = "02"  # 매수
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        # 필수 파라미터를 포함한 요청 데이터 준비
        request_body = order_data.copy()
        if "is_buy" in request_body:
            del request_body["is_buy"]  # API 요청에는 필요 없는 필드 제거
            
        # 필수 파라미터 설정
        request_body["RVSE_CNCL_DVSN_CD"] = "00"  # 정정취소구분코드 (00: 주문시 필수)
        
        response = requests.post(url, headers=headers, json=request_body, timeout=_HTTP_TIMEOUT)
        result = response.json()
        
        return result
    except Exception as e:
        logger.info(f"예약주문 접수 중 오류 발생: {str(e)}")
        raise

def inquire_psamount(params):
    """해외주식 매수가능금액 조회"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        tr_id = "TTTS3007R" if not settings.KIS_USE_MOCK else "VTTS3007R"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        # 기존 파라미터 유지
        base_params = {
            "CANO": params.get("CANO"),
            "ACNT_PRDT_CD": params.get("ACNT_PRDT_CD"),
            "OVRS_EXCG_CD": params.get("OVRS_EXCG_CD"),
            "OVRS_ORD_UNPR": params.get("OVRS_ORD_UNPR"),
            "ITEM_CD": params.get("ITEM_CD"),
            
            # 추가 필수 파라미터
            "AFHR_FLPR_YN": "N",  # 장후플래그여부
            "OFL_YN": "N",        # 오프라인여부
            "INQR_DVSN": "02",    # 조회구분 (02: 상세조회)
            "UNPR_DVSN": "01",    # 단가구분 (01: 기본값)
            "FUND_STTL_ICLD_YN": "N",  # 펀드결제포함여부
            "FNCG_AMT_AUTO_RDPT_YN": "N",  # 융자금액자동상환여부
            "PRCS_DVSN": "00",    # 처리구분 
            "CTX_AREA_FK100": "", # 연속조회검색조건100
            "CTX_AREA_NK100": ""  # 연속조회키100
        }
        
        response = requests.get(url, headers=headers, params=base_params, timeout=_HTTP_TIMEOUT)
        result = response.json()
        
        return result
    except Exception as e:
        logger.info(f"매수가능금액 조회 중 오류 발생: {str(e)}")
        raise


def _get_cash_usd_via_psamount_best_effort(*, ovrs_excg_cd: str = "NASD") -> tuple[float | None, float | None]:
    """
    KIS psamount 기반 주문가능 USD + KIS 제공 환율(exrt) 반환.
    반환: (cash_usd, usdkrw_exrt) — 실패 시 (None, None)
    """
    try:
        r = inquire_psamount(
            {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "ITEM_CD": "AAPL",
                "OVRS_ORD_UNPR": "1",
            }
        )
        if not isinstance(r, dict) or r.get("rt_cd") != "0":
            return None, None
        out = r.get("output") or {}
        if not isinstance(out, dict):
            return None, None

        def _f(k: str) -> float:
            try:
                return float(str(out.get(k) or "0").strip() or "0")
            except Exception:
                return 0.0

        vals = [
            _f("ord_psbl_frcr_amt"),
            _f("ovrs_ord_psbl_amt"),
        ]
        best = max(vals) if vals else 0.0
        exrt = _f("exrt") or None
        return (best if best > 0 else None), exrt
    except Exception:
        return None, None


def sync_cash_usd_to_db(*, ovrs_excg_cd: str = "NASD") -> bool:
    """KIS psamount 기반 현금(USD) + 환율 → holdings_summary 동기화."""
    try:
        cash, exrt = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd=ovrs_excg_cd)
        if cash is None or cash <= 0:
            return False
        supabase.table("holdings_summary").upsert(
            {
                "id": "main",
                "cash_usd": float(cash),
                "output2": {
                    "cash_source": "psamount",
                    "ovrs_excg_cd": ovrs_excg_cd,
                    "usdkrw_exrt": exrt,
                },
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="id",
        ).execute()
        return True
    except Exception:
        logger.warning("현금(USD) psamount 동기화 실패", exc_info=True)
        return False

# 추가: 해외주식 현재체결가 조회
def get_current_price(params):
    """해외주식 현재체결가 조회"""
    try:
        access_token = get_access_token()
        url = f"{settings.kis_base_url}/uapi/overseas-price/v1/quotations/price"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": "HHDFS00000300",
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
        result = response.json()
        
        return result
    except Exception as e:
        logger.info(f"현재체결가 조회 중 오류 발생: {str(e)}")
        raise

def get_overseas_nccs(params):
    """해외주식 미체결내역 조회"""
    try:
        access_token = get_access_token()
        
        if settings.KIS_USE_MOCK:
            url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-order"
            tr_id = "VTTS3035R"
        else:
            url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-nccs"
            tr_id = "TTTS3018R"
            
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
        result = response.json()
        
        if settings.KIS_USE_MOCK and 'output' in result and isinstance(result['output'], list):
            result['output'] = [item for item in result['output'] if int(item.get('nccs_qty', 0)) > 0]
        
        return result
    except Exception as e:
        logger.info(f"미체결내역 조회 중 오류 발생: {str(e)}")
        raise

def _normalize_order_inquiry_output(result: dict) -> dict:
    """inquire-order 응답 output 을 항상 list[dict] 로 맞춘다."""
    out = result.get("output")
    if out is None:
        result["output"] = []
    elif isinstance(out, dict):
        result["output"] = [out]
    elif not isinstance(out, list):
        result["output"] = []
    return result


def get_overseas_order_detail(params, *, only_unfilled_pending: bool = False):
    """해외주식 주문·체결 조회 (VTTS3035R / TTTS3035R).

    only_unfilled_pending=True 이면 미체결 잔량(nccs_qty)이 있는 행만 남긴다 (미체결 화면용).
    False 이면 필터 없이 정규화된 리스트를 반환한다 (체결 피드·당일 손익 집계용).
    """
    try:
        access_token = get_access_token()
        
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/inquire-order"
        tr_id = "VTTS3035R" if settings.KIS_USE_MOCK else "TTTS3035R"
        
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        logger.info(f"API 요청: {url}")
        logger.info(f"파라미터: {params}")
        
        response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
        
        logger.info(f"API 응답 상태 코드: {response.status_code}")
        logger.info(f"API 응답 본문: {response.text[:200] if response.text else '비어있음'}")
        
        if response.status_code == 404:
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "해당 API를 사용할 수 없습니다.",
                "output": []
            }
        
        if not response.text:
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "응답 데이터가 없습니다.",
                "output": []
            }
        
        try:
            result = response.json()
            result = _normalize_order_inquiry_output(result)
            if only_unfilled_pending and isinstance(result.get("output"), list):
                def _nq(item):
                    try:
                        return int(float(str(item.get("nccs_qty", "0") or "0")))
                    except (TypeError, ValueError):
                        return 0
                result["output"] = [item for item in result["output"] if _nq(item) > 0]
            return result
        except ValueError:
            return {
                "rt_cd": "0",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": []
            }
    except Exception as e:
        logger.info(f"주문체결내역 조회 중 오류 발생: {str(e)}")
        return {
            "rt_cd": "0", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": []
        }


def fetch_overseas_orders_for_period(ord_strt_dt: str, ord_end_dt: str, ovrs_excg_cd: str | None) -> dict:
    """해외주식 주문·체결 조회 (공식 ORD_STRT_DT / ORD_END_DT 파라미터)."""
    is_mock = settings.KIS_USE_MOCK
    ovrs = "" if is_mock else (ovrs_excg_cd or "NASD")
    params = {
        "CANO": settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "PDNO": "" if is_mock else "%",
        "ORD_STRT_DT": ord_strt_dt,
        "ORD_END_DT": ord_end_dt,
        "SLL_BUY_DVSN": "00",
        "CCLD_NCCS_DVSN": "00" if is_mock else "01",
        "OVRS_EXCG_CD": ovrs,
        "SORT_SQN": "AS",
        "ORD_DT": "",
        "ORD_GNO_BRNO": "00000",
        "ODNO": "",
        "CTX_AREA_FK200": "",
        "CTX_AREA_NK200": "",
    }
    return get_overseas_order_detail(params, only_unfilled_pending=False)


def get_merged_overseas_filled_orders(days: int = 30) -> list[dict]:
    """최근 days 일간 체결(또는 모의: 전체 후 ft_ccld_qty 필터) 주문 행을 거래소별로 합친다."""
    kst = pytz.timezone("Asia/Seoul")
    end = datetime.now(kst)
    start = end - timedelta(days=max(1, days))
    end_s = end.strftime("%Y%m%d")
    start_s = start.strftime("%Y%m%d")
    merged: list[dict] = []
    seen: set[tuple] = set()

    if settings.KIS_USE_MOCK:
        res = fetch_overseas_orders_for_period(start_s, end_s, "")
        if res.get("rt_cd") == "0" and isinstance(res.get("output"), list):
            merged.extend(res["output"])
    else:
        for ex in ("NASD", "NYSE", "AMEX"):
            res = fetch_overseas_orders_for_period(start_s, end_s, ex)
            if res.get("rt_cd") == "0" and isinstance(res.get("output"), list):
                merged.extend(res["output"])
            time.sleep(0.25)

    filled: list[dict] = []
    for item in merged:
        try:
            ccld = float(str(item.get("ft_ccld_qty", "0") or "0"))
        except (TypeError, ValueError):
            ccld = 0.0
        if ccld <= 0:
            continue
        key = (
            str(item.get("odno", "")),
            str(item.get("ord_dt", "")),
            str(item.get("pdno", "")),
            str(item.get("sll_buy_dvsn_cd", "")),
            str(item.get("ft_ccld_qty", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        filled.append(item)
    return filled

def get_overseas_order_resv_list(params):
    """해외주식 예약주문 조회"""
    try:
        if settings.KIS_USE_MOCK:
            # 모의투자에서는 지원되지 않으므로 안내 메시지 반환
            return {
                "rt_cd": "0",
                "msg_cd": "MOCK_UNSUPPORTED",
                "msg1": "모의투자 환경에서는 해외주식 예약주문조회 API를 지원하지 않습니다.",
                "output": []
            }
        
        # 실전투자 환경에서 API 호출
        access_token = get_access_token()
        
        # 거래소 코드에 따라 TR_ID 결정
        ovrs_excg_cd = params.get("OVRS_EXCG_CD", "")
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"] or not ovrs_excg_cd:
            # 미국 주식
            tr_id = "TTTT3039R"
        else:
            # 아시아 주식 (일본, 중국, 홍콩, 베트남)
            tr_id = "TTTS3014R"
            
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order-resv-list"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        
        # 디버깅 정보
        logger.info(f"예약주문조회 API 요청: {url}")
        logger.info(f"파라미터: {params}")
        
        response = requests.get(url, headers=headers, params=params, timeout=_HTTP_TIMEOUT)
        
        # 응답 확인
        logger.info(f"API 응답 상태 코드: {response.status_code}")
        
        if response.status_code != 200:
            return {
                "rt_cd": "1",
                "msg_cd": f"HTTP_{response.status_code}",
                "msg1": f"API 호출 실패: HTTP {response.status_code}",
                "output": []
            }
        
        if not response.text:
            return {
                "rt_cd": "0",
                "msg_cd": "NODATA",
                "msg1": "응답 데이터가 없습니다.",
                "output": []
            }
        
        try:
            result = response.json()
            return result
        except ValueError:
            return {
                "rt_cd": "1",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": []
            }
    except Exception as e:
        logger.info(f"예약주문조회 중 오류 발생: {str(e)}")
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": []
        }

def order_overseas_stock(order_data):
    """해외주식 주문 실행"""
    try:
        # 토큰 가져오기
        access_token = get_access_token()
        
        # 기본 계좌정보 설정
        if "CANO" not in order_data or not order_data["CANO"]:
            order_data["CANO"] = settings.KIS_CANO
        if "ACNT_PRDT_CD" not in order_data or not order_data["ACNT_PRDT_CD"]:
            order_data["ACNT_PRDT_CD"] = settings.KIS_ACNT_PRDT_CD
            
        is_mock = settings.KIS_USE_MOCK
        
        # 매수/매도 여부 확인
        is_buy = order_data.get("is_buy", True)
        
        # 거래소 코드에 따라 tr_id 결정
        ovrs_excg_cd = order_data.get("OVRS_EXCG_CD", "")
        
        # tr_id 결정 (매수/매도 및 거래소에 따라 다름)
        if ovrs_excg_cd in ["NASD", "NYSE", "AMEX"]:
            # 미국 주식
            if is_buy:
                tr_id = "VTTT1002U" if is_mock else "TTTT1002U"  # 미국 매수
            else:
                tr_id = "VTTT1001U" if is_mock else "TTTT1006U"  # 미국 매도
        elif ovrs_excg_cd == "TKSE":
            # 일본 주식
            if is_buy:
                tr_id = "VTTS0308U" if is_mock else "TTTS0308U"  # 일본 매수
            else:
                tr_id = "VTTS0307U" if is_mock else "TTTS0307U"  # 일본 매도
        elif ovrs_excg_cd == "SHAA":
            # 상해 주식
            if is_buy:
                tr_id = "VTTS0202U" if is_mock else "TTTS0202U"  # 상해 매수
            else:
                tr_id = "VTTS1005U" if is_mock else "TTTS1005U"  # 상해 매도
        elif ovrs_excg_cd == "SEHK":
            # 홍콩 주식
            if is_buy:
                tr_id = "VTTS1002U" if is_mock else "TTTS1002U"  # 홍콩 매수
            else:
                tr_id = "VTTS1001U" if is_mock else "TTTS1001U"  # 홍콩 매도
        elif ovrs_excg_cd == "SZAA":
            # 심천 주식
            if is_buy:
                tr_id = "VTTS0305U" if is_mock else "TTTS0305U"  # 심천 매수
            else:
                tr_id = "VTTS0304U" if is_mock else "TTTS0304U"  # 심천 매도
        elif ovrs_excg_cd in ["HASE", "VNSE"]:
            # 베트남 주식
            if is_buy:
                tr_id = "VTTS0311U" if is_mock else "TTTS0311U"  # 베트남 매수
            else:
                tr_id = "VTTS0310U" if is_mock else "TTTS0310U"  # 베트남 매도
        else:
            return {
                "rt_cd": "1",
                "msg_cd": "INVALID_EXCHANGE",
                "msg1": f"지원되지 않는 거래소 코드: {ovrs_excg_cd}",
                "output": {}
            }
        
        # API 요청 URL 및 헤더 설정
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id
        }
        
        # 필수 파라미터 준비 (요청 본문에서 is_buy 제거)
        request_body = order_data.copy()
        if "is_buy" in request_body:
            del request_body["is_buy"]
        
        # 기본 값 설정
        if "ORD_SVR_DVSN_CD" not in request_body:
            request_body["ORD_SVR_DVSN_CD"] = "0"
        
        # 주문구분 설정 (기본값: 지정가)
        if "ORD_DVSN" not in request_body:
            request_body["ORD_DVSN"] = "00"  # 지정가
        
        # 디버깅 정보 출력
        logger.info(f"해외주식 주문 API 요청: {url}")
        logger.info(f"헤더: {headers}")
        logger.info(f"요청 본문: {request_body}")
        
        # API 호출
        response = requests.post(url, headers=headers, json=request_body, timeout=_HTTP_TIMEOUT)
        
        # 응답 확인
        logger.info(f"API 응답 상태 코드: {response.status_code}")
        logger.info(f"API 응답 본문: {response.text[:200] if response.text else '비어있음'}")
        
        # 응답 처리: 모의투자 등에서 HTTP 500과 함께 KIS 표준 JSON(rt_cd 포함)이 오는 경우가 있어 본문을 우선 해석한다.
        if response.text:
            try:
                result = response.json()
                if isinstance(result, dict) and "rt_cd" in result:
                    return result
            except ValueError:
                pass

        if response.status_code != 200:
            return {
                "rt_cd": "1",
                "msg_cd": f"HTTP_{response.status_code}",
                "msg1": f"API 호출 실패: HTTP {response.status_code}",
                "output": {},
            }

        if not response.text:
            return {
                "rt_cd": "1",
                "msg_cd": "EMPTY",
                "msg1": "응답 본문이 비어 있습니다.",
                "output": {},
            }

        try:
            result = response.json()
            # 주문 내역을 DB에 저장 (옵션)
            # save_order_history(request_body, result)
            return result
        except ValueError:
            return {
                "rt_cd": "1",
                "msg_cd": "PARSEERR",
                "msg1": "응답 파싱 오류",
                "output": {},
            }
    except Exception as e:
        logger.exception("해외주식 주문 실패: %s", e)
        return {
            "rt_cd": "1", 
            "msg_cd": "ERROR",
            "msg1": f"API 호출 오류: {str(e)}",
            "output": {}
        }

def _tr_id_overseas_order_rvsecncl(*, exchange_code: str) -> str:
    """
    해외주식 정정/취소 주문 TR_ID 선택.

    참고(오픈소스 구현 기준):
    - 미국(정규) 정정/취소: TTTT1004U (실전), VTTT1004U (모의)
    """
    ex = (exchange_code or "").strip().upper()
    is_mock = bool(settings.KIS_USE_MOCK)
    if ex in ("NASD", "NYSE", "AMEX"):
        return "VTTT1004U" if is_mock else "TTTT1004U"
    # 기타 거래소는 이 프로젝트에서 초기화 대상이 사실상 미국이므로,
    # 미지원은 명확히 실패로 처리한다.
    raise ValueError(f"정정/취소 TR_ID 미지원 거래소: {ex}")


def cancel_overseas_order(*, exchange_code: str, ticker: str, orgn_odno: str) -> dict:
    """해외주식 정정취소주문(v1_해외주식-003)으로 주문 취소 시도."""
    try:
        access_token = get_access_token()
        tr_id = _tr_id_overseas_order_rvsecncl(exchange_code=exchange_code)
        url = f"{settings.kis_base_url}/uapi/overseas-stock/v1/trading/order-rvsecncl"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appkey": settings.KIS_APPKEY,
            "appsecret": settings.KIS_APPSECRET,
            "tr_id": tr_id,
        }
        body = {
            "OVRS_EXCG_CD": exchange_code,
            "PDNO": ticker,
            "ORGN_ODNO": orgn_odno,
            "RVSE_CNCL_DVSN_CD": "02",  # 01=정정, 02=취소
            "ORD_QTY": "0",
            "OVRS_ORD_UNPR": "0",
        }
        resp = requests.post(url, headers=headers, json=body, timeout=_HTTP_TIMEOUT)
        try:
            result = resp.json() if resp.text else {"rt_cd": "1", "msg_cd": "EMPTY", "msg1": "응답 본문이 비어 있습니다."}
        except Exception:
            result = {"rt_cd": "1", "msg_cd": "PARSEERR", "msg1": "응답 파싱 오류"}
        result["_http_status"] = resp.status_code
        result["_request"] = {"url": url, "tr_id": tr_id, "body": body}
        return result
    except Exception as e:
        return {"rt_cd": "1", "msg_cd": "ERROR", "msg1": f"취소 주문 오류: {str(e)}"}


def cancel_all_unfilled_overseas_orders(*, ny_trading_date: str | None = None) -> dict:
    """
    미체결(주문잔량) 주문을 최대한 취소한다.
    - 모의투자: inquire-order 기반
    - 실전: inquire-order 기반(프로젝트 구현은 get_overseas_order_detail)
    """
    summary: dict = {"attempted": True, "success": True, "canceled": [], "failed": [], "skipped": []}
    try:
        now_ny = datetime.now(pytz.timezone("America/New_York"))
        ord_dt = (ny_trading_date or now_ny.strftime("%Y%m%d")).strip()
        # 오늘 주문·체결 조회에서 미체결만 걸러 취소 시도
        res = fetch_overseas_orders_for_period(ord_dt, ord_dt, "" if settings.KIS_USE_MOCK else "NASD")
        out = res.get("output") if isinstance(res, dict) else []
        if not isinstance(out, list):
            out = []

        def _nq(item: dict) -> int:
            try:
                return int(float(str(item.get("nccs_qty", "0") or "0")))
            except Exception:
                return 0

        unfilled = [it for it in out if isinstance(it, dict) and _nq(it) > 0]
        summary["unfilled_count"] = len(unfilled)
        for it in unfilled:
            ticker = str(it.get("pdno", "") or "").strip()
            orgn_odno = str(it.get("odno", "") or "").strip()
            ex = str(it.get("ovrs_excg_cd", "") or "NASD").strip()
            if not ticker or not orgn_odno:
                summary["skipped"].append({"ticker": ticker, "odno": orgn_odno, "reason": "ticker/odno 비어있음"})
                continue
            r = cancel_overseas_order(exchange_code=ex, ticker=ticker, orgn_odno=orgn_odno)
            ok = bool(isinstance(r, dict) and r.get("rt_cd") == "0")
            if ok:
                summary["canceled"].append({"ticker": ticker, "odno": orgn_odno, "exchange_code": ex, "result": r})
            else:
                summary["failed"].append({"ticker": ticker, "odno": orgn_odno, "exchange_code": ex, "result": r})
                summary["success"] = False
            time.sleep(0.5)
        summary["canceled_count"] = len(summary["canceled"])
        summary["failed_count"] = len(summary["failed"])
        summary["skipped_count"] = len(summary["skipped"])
        return summary
    except Exception as e:
        summary["success"] = False
        summary["error"] = str(e)
        return summary


def reset_mock_investment(*, max_total_sec: int = 180) -> dict:
    """모의투자 리셋: 전체 보유 종목 전량 매도.

    리셋 후 스케줄러는 그대로 유지되며, 다음 장 오픈 시 정상 매수/매도 진행.
    Returns:
        dict: sold / failed / skipped 항목 리스트 + 전체 성공 여부
    """
    def _snapshot_holdings() -> tuple[dict | None, list[dict]]:
        """KIS 잔고에서 (raw_result, remaining[]) 추출.

        주의:
        - KIS 응답에는 보유수량(ovrs_cblc_qty)과 주문가능수량(ord_psbl_qty)가 따로 있다.
        - '전량 매도' 목표는 보유수량 기준이며, 주문가능수량이 0이면 미체결/락 등으로 매도가 막힌 상태일 수 있다.
        """
        bal = get_all_overseas_balances()
        if bal.get("rt_cd") != "0":
            return bal, []
        rem: list[dict] = []
        for h in bal.get("output1", []) or []:
            ticker = (h.get("ovrs_pdno") or "").strip()
            exchange_code = (h.get("ovrs_excg_cd") or "NASD").strip()
            try:
                qty_holding = int(float(str(h.get("ovrs_cblc_qty") or "0") or "0"))
            except Exception:
                qty_holding = 0
            try:
                qty_sellable = int(float(str(h.get("ord_psbl_qty") or "0") or "0"))
            except Exception:
                qty_sellable = 0
            if ticker and qty_holding > 0:
                rem.append(
                    {
                        "ticker": ticker,
                        "exchange_code": exchange_code,
                        "qty": qty_holding,
                        "qty_holding": qty_holding,
                        "qty_sellable": qty_sellable,
                    }
                )
        return bal, rem

    started_at = datetime.now(timezone.utc)
    summary: dict = {
        "success": True,
        "sold": [],
        "failed": [],
        "skipped": [],
        "rounds": 0,
        "settled": False,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": None,
        "sold_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "remaining_count": None,
        "remaining_holdings": [],
        "progress": [],
    }

    # 전량매도는 체결 지연/부분체결/레이트리밋으로 한 번에 끝나지 않을 수 있어,
    # "총 시간 제한 내에서" 반복 시도한다.
    max_total_sec = int(max(10, max_total_sec))  # 최소 10초
    deadline = time.time() + max_total_sec
    round_idx = 0
    last_remaining: list[dict] = []

    # 중복 로그 폭증을 막기 위한 set(티커별 최근 실패 메시지)
    last_fail_msg: dict[str, str] = {}

    while time.time() < deadline:
        round_idx += 1
        summary["rounds"] = round_idx

        bal, remaining = _snapshot_holdings()
        if bal is not None and bal.get("rt_cd") != "0":
            summary["success"] = False
            summary["error"] = f"잔고 조회 실패: {bal.get('msg1', '알 수 없는 오류')}"
            break

        # 최초부터 보유가 없으면 즉시 완료
        if not remaining:
            summary["message"] = "보유 종목이 없습니다."
            summary["settled"] = True
            break

        last_remaining = remaining
        summary["progress"].append(
            {
                "round": round_idx,
                "remaining_count": len(remaining),
                "remaining": remaining,
            }
        )

        # 주문가능수량이 0인 보유가 있으면, 미체결 주문이 수량을 묶고 있을 가능성이 높다.
        # 이 경우 "미체결 취소 → 전량매도" 순서로 진행해야 초기화가 끝난다.
        if any(int(it.get("qty_sellable") or 0) <= 0 for it in remaining):
            try:
                cancel_summary = cancel_all_unfilled_overseas_orders()
            except Exception as ce:
                cancel_summary = {"attempted": True, "success": False, "error": str(ce)}
            summary.setdefault("cancel_unfilled_orders", []).append({"round": round_idx, **(cancel_summary or {})})
            # 취소 반영 대기
            time.sleep(2)

        # 1) 현재 남은 종목들에 대해 매도 주문 시도
        for item in remaining:
            ticker = item["ticker"]
            exchange_code = item["exchange_code"]
            qty = int(item["qty"])
            qty_sellable = int(item.get("qty_sellable") or 0)

            if not ticker or qty <= 0:
                summary["skipped"].append({"ticker": ticker, "reason": "수량 0 또는 티커 없음", "round": round_idx})
                continue
            if qty_sellable <= 0:
                # 주문가능수량이 0이어도 보유수량은 남아있을 수 있다(미체결/락/제한 등).
                # 그래도 전량매도 목표이므로 매도 주문을 시도하되, 결과 JSON에 원인을 남긴다.
                summary["skipped"].append(
                    {"ticker": ticker, "reason": "주문가능수량(ord_psbl_qty)=0 (미체결/락 가능)", "round": round_idx}
                )

            api_exchange_code = "NAS" if exchange_code == "NASD" else "NYS" if exchange_code == "NYSE" else exchange_code

            # 현재가 조회 (rate limit 재시도)
            price_result = None
            for _attempt in range(3):
                price_result = get_current_price({"AUTH": "", "EXCD": api_exchange_code, "SYMB": ticker})
                if price_result.get("rt_cd") == "0":
                    break
                if "초당" in str(price_result.get("msg1", "")):
                    logger.warning("리셋: %s 현재가 rate limit → 2초 후 재시도", ticker)
                    time.sleep(2)
                else:
                    break

            if (price_result or {}).get("rt_cd") != "0":
                msg = (price_result or {}).get("msg1", "현재가 조회 실패")
                if last_fail_msg.get(ticker) != msg:
                    logger.error("리셋 중 %s 현재가 조회 실패: %s", ticker, msg)
                    last_fail_msg[ticker] = msg
                summary["failed"].append({"ticker": ticker, "error": msg, "round": round_idx})
                summary["success"] = False
                time.sleep(1)
                continue

            current_price = 0.0
            try:
                current_price = float((price_result or {}).get("output", {}).get("last", 0))
            except (TypeError, ValueError):
                pass

            if current_price <= 0:
                msg = f"유효하지 않은 현재가: {current_price}"
                if last_fail_msg.get(ticker) != msg:
                    logger.error("리셋 중 %s 현재가 오류: %s", ticker, msg)
                    last_fail_msg[ticker] = msg
                summary["failed"].append({"ticker": ticker, "error": msg, "round": round_idx})
                summary["success"] = False
                time.sleep(1)
                continue

            time.sleep(1)  # 현재가 조회 후 주문 전 1초 대기

            # 모의투자 API는 가격 포맷에 민감한 케이스가 있어 2자리로 고정한다.
            price_str = f"{float(current_price):.2f}"

            order_data = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": exchange_code,
                "PDNO": ticker,
                # 초기화/리셋은 "보유 0"이 목표.
                # - 모의투자(VTS)는 "지정가만 가능한 상품" 오류가 자주 나서 지정가(00)로 강제한다.
                # - 실전은 시장가(01)가 더 잘 체결되지만, 지정가(00)도 동작하므로 실패 시 재시도 루프가 커버한다.
                "ORD_DVSN": "00" if bool(settings.KIS_USE_MOCK) else "01",
                "ORD_QTY": str(qty),
                "OVRS_ORD_UNPR": price_str,
                "is_buy": False,
            }

            # 주문 (rate limit 재시도)
            order_result = None
            backoff = 2.0
            for _attempt in range(3):
                order_result = order_overseas_stock(order_data)
                msg1 = order_result.get("msg1", "") if isinstance(order_result, dict) else ""
                if isinstance(order_result, dict) and order_result.get("rt_cd") == "0":
                    break
                if "초당" in str(msg1) or "거래건수" in str(msg1):
                    logger.warning("리셋: %s 주문 rate limit → %s초 후 재시도", ticker, backoff)
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    break

            msg1 = order_result.get("msg1", "") if isinstance(order_result, dict) else ""
            order_success = bool(isinstance(order_result, dict) and order_result.get("rt_cd") == "0")

            from app.services.daily_log_service import save_order
            from app.api.routes.stocks import TICKER_TO_STOCK
            _stock_name = TICKER_TO_STOCK.get(ticker, ticker)
            _ny_date = datetime.now(pytz.timezone("America/New_York")).strftime("%Y-%m-%d")

            if order_success:
                logger.info("리셋: %s %s주 매도 주문 접수 @ $%s", ticker, qty, current_price)
                summary["sold"].append(
                    {
                        "ticker": ticker,
                        "quantity": qty,
                        "price": current_price,
                        "price_str": price_str,
                        "exchange_code": exchange_code,
                        "round": round_idx,
                    }
                )
                try:
                    save_order(
                        side="sell",
                        ticker=ticker,
                        stock_name=_stock_name,
                        exchange_code=exchange_code,
                        quantity=qty,
                        limit_price=current_price,
                        order_type=order_data.get("ORD_DVSN"),
                        rt_cd=order_result.get("rt_cd"),
                        api_message=msg1,
                        success=True,
                        source="reset",
                        payload={"reason": "reset_all_positions", "order_result": order_result},
                        ny_trading_date=_ny_date,
                    )
                except Exception as _se:
                    logger.warning("리셋: %s save_order 실패(무시): %s", ticker, _se)
            else:
                if last_fail_msg.get(ticker) != msg1:
                    logger.error("리셋: %s 매도 실패: %s", ticker, msg1)
                    last_fail_msg[ticker] = msg1
                try:
                    save_order(
                        side="sell",
                        ticker=ticker,
                        stock_name=_stock_name,
                        exchange_code=exchange_code,
                        quantity=qty,
                        limit_price=current_price,
                        order_type=order_data.get("ORD_DVSN"),
                        rt_cd=(order_result or {}).get("rt_cd"),
                        api_message=msg1,
                        success=False,
                        source="reset",
                        payload={"reason": "reset_all_positions", "order_result": order_result},
                        ny_trading_date=_ny_date,
                    )
                except Exception as _se:
                    logger.warning("리셋: %s 실패 save_order 실패(무시): %s", ticker, _se)
                summary["failed"].append(
                    {
                        "ticker": ticker,
                        "quantity": qty,
                        "error": msg1,
                        "round": round_idx,
                        "exchange_code": exchange_code,
                        "order_data": {
                            "OVRS_EXCG_CD": exchange_code,
                            "PDNO": ticker,
                            "ORD_DVSN": order_data.get("ORD_DVSN"),
                            "ORD_QTY": order_data.get("ORD_QTY"),
                            "OVRS_ORD_UNPR": order_data.get("OVRS_ORD_UNPR"),
                        },
                        "order_result": order_result,
                    }
                )
                summary["success"] = False

            time.sleep(1)

        # 모의투자에서 특정 오류는 반복해도 해결되지 않는 경우가 많다(예: 잔고내역 없음).
        # 이런 경우에는 오래 기다리지 말고 빠르게 종료해 DB-only 초기화로 넘어가게 한다.
        if settings.KIS_USE_MOCK:
            try:
                last_errs = [str(x.get("error") or "") for x in (summary.get("failed") or [])[-5:]]
                if any("모의투자 잔고내역이 없습니다" in e for e in last_errs):
                    break
            except Exception:
                pass

        # 2) 체결/잔고 0 “정착(settle)” 대기(남은 시간이 허용하는 범위)
        settle_timeout_sec = min(45, max(5, int(deadline - time.time())))
        settle_poll_sec = 3
        waited = 0
        while waited <= settle_timeout_sec:
            _bal2, rem2 = _snapshot_holdings()
            if not rem2:
                summary["settled"] = True
                break
            time.sleep(settle_poll_sec)
            waited += settle_poll_sec

        if summary.get("settled") is True:
            break

        # 다음 라운드까지 잠깐 대기(레이트리밋/체결지연 완화)
        time.sleep(3)

    # 종료 시점 상태 정리(항상 카운트/잔여 포함)
    try:
        _bal3, rem3 = _snapshot_holdings()
        summary["remaining_holdings"] = rem3 or []
        summary["remaining_count"] = len(summary["remaining_holdings"])
        if summary["remaining_count"] == 0:
            summary["settled"] = True
    except Exception:
        summary["remaining_holdings"] = last_remaining or []
        summary["remaining_count"] = len(summary["remaining_holdings"])
        summary["success"] = False
        summary["settled"] = False

    summary["sold_count"] = len(summary.get("sold") or [])
    summary["failed_count"] = len(summary.get("failed") or [])
    summary["skipped_count"] = len(summary.get("skipped") or [])

    if summary.get("settled") is not True:
        summary["success"] = False

    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    return summary


def create_conditional_orders(params):
    """
    특정 가격에 도달했을 때 자동으로 실행되는 조건부 주문 설정
    손절매(stop loss)와 이익실현(take profit) 주문을 동시에 설정
    """
    try:
        # 1. 해외주식 잔고 조회
        balance_result = get_overseas_balance()
        
        if balance_result.get("rt_cd") != "0":
            return {
                "rt_cd": "1",
                "msg_cd": "BALANCE_ERROR",
                "msg1": f"잔고 조회 실패: {balance_result.get('msg1', '알 수 없는 오류')}",
                "output": {}
            }
        
        # 2. 종목 정보 찾기
        pdno = params.get("pdno")
        ovrs_excg_cd = params.get("ovrs_excg_cd")
        
        holdings = balance_result.get("output1", [])
        target_holding = None
        
        for holding in holdings:
            if holding.get("ovrs_pdno") == pdno:
                target_holding = holding
                break
        
        if not target_holding:
            return {
                "rt_cd": "1",
                "msg_cd": "NO_HOLDING",
                "msg1": f"해당 종목({pdno})을 보유하고 있지 않습니다.",
                "output": {}
            }
        
        # 3. 기준 가격, 손절매 가격, 이익실현 가격 계산
        base_price = params.get("base_price")
        if not base_price:
            # 매수 평균단가를 기준 가격으로 사용
            base_price = float(target_holding.get("pchs_avg_pric", "0"))
            
        if base_price <= 0:
            return {
                "rt_cd": "1",
                "msg_cd": "INVALID_PRICE",
                "msg1": "유효하지 않은 기준 가격입니다.",
                "output": {}
            }
        
        # 손절매, Profit Taking 퍼센트 설정
        stop_loss_percent = params.get("stop_loss_percent", -5.0)
        take_profit_percent = params.get("take_profit_percent", 5.0)
        
        # 가격 계산
        stop_loss_price = round(base_price * (1 + stop_loss_percent/100), 2)
        take_profit_price = round(base_price * (1 + take_profit_percent/100), 2)
        
        # 주문 수량 설정 (params에 quantity가 없으면 전체 보유 수량 사용)
        quantity = params.get("quantity", target_holding.get("ord_psbl_qty", "0"))
        
        # 4. 손절매 및 이익실현 주문 생성
        order_results = []
        
        # 손절매 주문 생성 (마이너스이면 실행)
        if stop_loss_percent < 0:
            stop_loss_order = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "PDNO": pdno,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "FT_ORD_QTY": quantity,
                "FT_ORD_UNPR3": str(stop_loss_price),
                "is_buy": False,  # 매도
                "ORD_DVSN": "00"  # 지정가
            }
            
            stop_loss_result = overseas_order_resv(stop_loss_order)
            stop_loss_result["order_type"] = "stop_loss"
            order_results.append(stop_loss_result)
        
        # 이익실현 주문 생성 (플러스이면 실행)
        if take_profit_percent > 0:
            take_profit_order = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "PDNO": pdno,
                "OVRS_EXCG_CD": ovrs_excg_cd,
                "FT_ORD_QTY": quantity,
                "FT_ORD_UNPR3": str(take_profit_price),
                "is_buy": False,  # 매도
                "ORD_DVSN": "00"  # 지정가
            }
            
            take_profit_result = overseas_order_resv(take_profit_order)
            take_profit_result["order_type"] = "take_profit"
            order_results.append(take_profit_result)
        
        # 5. 결과 반환
        success_count = sum(1 for r in order_results if r.get("rt_cd") == "0")
        
        return {
            "rt_cd": "0" if success_count > 0 else "1",
            "msg_cd": "SUCCESS" if success_count == len(order_results) else "PARTIAL_SUCCESS" if success_count > 0 else "FAILED",
            "msg1": f"{success_count}/{len(order_results)} 주문이 성공적으로 처리되었습니다.",
            "base_price": base_price,
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "order_results": order_results
        }
        
    except Exception as e:
        logger.exception("조건부 주문 생성 실패: %s", e)
        return {
            "rt_cd": "1",
            "msg_cd": "ERROR",
            "msg1": f"조건부 주문 생성 중 오류 발생: {str(e)}",
            "output": {}
        }


# ─── Supabase 동기화 / 읽기 ──────────────────────────────────────────────────


def sync_holdings_to_db() -> bool:
    """KIS 해외주식 잔고 → Supabase holdings 테이블 동기화."""
    try:
        exchanges = ["NASD", "NYSE", "AMEX"]
        rows: list[dict] = []
        seen: set[str] = set()
        cash_usd = 0.0
        output2_best: dict = {}

        got_valid_response = False
        for exchange in exchanges:
            try:
                result = get_overseas_balance(exchange)
                if result.get("rt_cd") != "0":
                    continue
                got_valid_response = True
                for h in result.get("output1", []):
                    ticker = (h.get("ovrs_pdno") or "").strip()
                    if not ticker or ticker in seen:
                        continue
                    seen.add(ticker)
                    rows.append({
                        "ticker": ticker,
                        "name": h.get("ovrs_item_name", ""),
                        "qty": h.get("ovrs_cblc_qty", "0"),
                        "avg_price": h.get("pchs_avg_pric", "0"),
                        "current_price": h.get("now_pric2", "0"),
                        "pnl_amount": h.get("frcr_evlu_pfls_amt", "0"),
                        "pnl_rate": h.get("evlu_pfls_rt", "0"),
                        "buy_amount": h.get("frcr_buy_amt_smtl1", "0"),
                        "raw": h,
                        "synced_at": datetime.now(timezone.utc).isoformat(),
                    })
                o2 = result.get("output2") or {}
                output2_best = o2
                for k in ("ovrs_ord_psbl_amt", "ord_psbl_frcr_amt"):
                    v = float(str(o2.get(k) or "0") or "0")
                    if v > cash_usd:
                        cash_usd = v
                time.sleep(1.1)
            except Exception as ex:
                logger.warning("sync_holdings_to_db %s 조회 실패: %s", exchange, ex)

        if rows:
            supabase.table("holdings").upsert(rows, on_conflict="ticker").execute()

        # KIS에서 유효한 응답을 받은 경우에만 stale 삭제 (전 거래소 실패 시 DB 보존)
        if got_valid_response:
            existing = supabase.table("holdings").select("ticker").execute()
            current_tickers = {r["ticker"] for r in rows}
            stale = [r["ticker"] for r in (existing.data or []) if r["ticker"] not in current_tickers]
            if stale:
                supabase.table("holdings").delete().in_("ticker", stale).execute()

        # 현금/요약 동기화
        #
        # 주의: 장외/네트워크 오류 등으로 KIS output2(주문가능외화)가 비거나 조회 실패하면 cash_usd=0으로 계산될 수 있다.
        # 이때 초기화 시드(예: 5억→USD)나 직전 정상 값까지 0으로 덮어쓰면 프론트에서 "예수금 0"처럼 보인다.
        # 따라서 cash_usd가 유효(>0)할 때만 업데이트하고, 0이면 기존 값을 보존한다(best-effort).
        cash_to_write = cash_usd
        if cash_to_write <= 0:
            # output2에 현금 필드가 비는 케이스(특히 모의투자) 보완: psamount로 주문가능 외화 조회
            ps_cash, _ = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd="NASD")
            if ps_cash and ps_cash > 0:
                cash_to_write = ps_cash
        if cash_to_write <= 0:
            try:
                prev = supabase.table("holdings_summary").select("cash_usd").eq("id", "main").limit(1).execute()
                prev_row = (prev.data or [{}])[0]
                prev_cash = float(prev_row.get("cash_usd") or 0)
                if prev_cash > 0:
                    cash_to_write = prev_cash
            except Exception:
                pass

        supabase.table("holdings_summary").upsert(
            {
                "id": "main",
                "cash_usd": cash_to_write,
                "output2": output2_best,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="id",
        ).execute()

        logger.info("holdings 동기화 완료: %d개 / 현금 %.2f USD", len(rows), cash_to_write)
        return True
    except Exception as e:
        logger.error("holdings 동기화 오류: %s", e)
        return False


def sync_order_fills_to_db(days: int = 30) -> bool:
    """KIS 체결 내역 → Supabase order_fills 테이블 동기화."""
    try:
        fills = get_merged_overseas_filled_orders(days=days)
        rows = []
        for item in fills:
            key = "|".join([
                str(item.get("odno", "")),
                str(item.get("ord_dt", "")),
                str(item.get("pdno", "")),
                str(item.get("sll_buy_dvsn_cd", "")),
                str(item.get("ft_ccld_qty", "")),
            ])
            rows.append({
                "fill_key": key,
                "odno": item.get("odno", ""),
                "ord_dt": item.get("ord_dt", ""),
                "ord_tmd": item.get("ord_tmd", ""),
                "ticker": item.get("pdno", ""),
                "name": item.get("prdt_name", ""),
                "side_cd": item.get("sll_buy_dvsn_cd", ""),
                "side_name": item.get("sll_buy_dvsn_cd_name", ""),
                "qty": item.get("ft_ccld_qty", "0"),
                "price": item.get("ft_ccld_unpr3", "0"),
                "amount": item.get("ft_ccld_amt3", "0"),
                "exchange": item.get("ovrs_excg_cd", ""),
                "status": item.get("prcs_stat_name", ""),
                "raw": item,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            })
        if rows:
            supabase.table("order_fills").upsert(rows, on_conflict="fill_key").execute()
        logger.info("order_fills 동기화 완료: %d개", len(rows))
        return True
    except Exception as e:
        logger.error("order_fills 동기화 오류: %s", e)
        return False


def get_holdings_from_db() -> dict:
    """Supabase holdings 테이블 → KisOverseasBalance 형식으로 반환."""
    try:
        h_resp = supabase.table("holdings").select("raw").order("ticker").execute()
        s_resp = supabase.table("holdings_summary").select("cash_usd").eq("id", "main").execute()
        output1 = [r["raw"] for r in (h_resp.data or []) if r.get("raw")]
        cash = float((s_resp.data or [{}])[0].get("cash_usd") or 0)
        return {"rt_cd": "0", "output1": output1, "output2": {}, "cashUsdBestEffort": cash}
    except Exception as e:
        logger.error("holdings DB 조회 오류: %s", e)
        return {"rt_cd": "1", "output1": [], "output2": {}}


def get_order_fills_from_db(days: int = 30) -> list[dict]:
    """Supabase order_fills 테이블 → 체결 내역 리스트 반환."""
    try:
        kst = pytz.timezone("Asia/Seoul")
        cutoff = (datetime.now(kst) - timedelta(days=days)).strftime("%Y%m%d")
        resp = (
            supabase.table("order_fills")
            .select("raw")
            .gte("ord_dt", cutoff)
            .order("ord_dt", desc=True)
            .execute()
        )
        rows = [r["raw"] for r in (resp.data or []) if r.get("raw")]

        # 모의투자(VTS) 환경에서는 KIS inquire-order(체결) API가 404로 막히는 경우가 있어
        # order_fills 테이블이 비게 된다. 이 경우 프론트의 "당일 체결 현금"이 항상 0이 되어 UX가 깨지므로,
        # 최소한의 대체값으로 order_history(주문 성공 로그)를 "체결로 간주한 현금흐름" 형태로 변환해 반환한다.
        if not rows and settings.KIS_USE_MOCK:
            try:
                hist = get_order_history_from_db()
                pseudo: list[dict] = []
                # days 필터(최소): ny_trading_date가 YYYY-MM-DD 이므로 문자열 비교 대신 안전하게 파싱
                now_ny = datetime.now(pytz.timezone("America/New_York")).date()
                min_date = now_ny - timedelta(days=max(1, days))
                for h in hist:
                    if not (h.get("success") is True):
                        continue
                    side = (h.get("side") or "").lower()
                    if side not in ("buy", "sell"):
                        continue
                    ny_date = (h.get("ny_trading_date") or "").strip()
                    if len(ny_date) < 10:
                        continue
                    try:
                        d = datetime.strptime(ny_date[:10], "%Y-%m-%d").date()
                    except ValueError:
                        continue
                    if d < min_date:
                        continue

                    qty = h.get("quantity")
                    lp = h.get("limit_price")
                    try:
                        qty_f = float(qty) if qty is not None else 0.0
                        lp_f = float(lp) if lp is not None else 0.0
                    except (TypeError, ValueError):
                        continue
                    if qty_f <= 0 or lp_f <= 0:
                        continue

                    amt = qty_f * lp_f
                    pseudo.append(
                        {
                            "odno": str(h.get("id") or ""),
                            "ord_dt": ny_date[:10].replace("-", ""),  # YYYYMMDD
                            "ord_tmd": "",
                            "pdno": str(h.get("ticker") or ""),
                            "prdt_name": h.get("stock_name") or "",
                            # KIS 규칙: 매수 02(외화 지출), 매도 01(외화 입금)
                            "sll_buy_dvsn_cd": "02" if side == "buy" else "01",
                            "sll_buy_dvsn_cd_name": "매수" if side == "buy" else "매도",
                            "ft_ccld_qty": str(int(qty_f)) if float(qty_f).is_integer() else str(qty_f),
                            "ft_ccld_unpr3": str(lp_f),
                            "ft_ccld_amt3": str(amt),
                            "ovrs_excg_cd": h.get("exchange_code") or "",
                            "prcs_stat_name": "PSEUDO_FILL_FROM_ORDER_HISTORY",
                        }
                    )
                # 최신이 위로 오도록(프론트 sort는 ord_dt+ord_tmd 기반이므로 ord_tmd가 비면 날짜로만 정렬됨)
                pseudo.sort(key=lambda r: str(r.get("ord_dt") or ""), reverse=True)
                return pseudo
            except Exception:
                # fallback 실패는 조용히: 그냥 빈 리스트 유지
                return rows

        return rows
    except Exception as e:
        logger.error("order_fills DB 조회 오류: %s", e)
        return []


def get_order_history_from_db() -> list[dict]:
    """Supabase order_history 테이블 → 주문 이력(매수/매도) 전체 반환."""
    try:
        resp = (
            supabase.table("order_history")
            .select("*")
            .order("kst_at", desc=True)
            .execute()
        )
        rows = list(resp.data or [])

        # 과거 데이터(이전 버전)는 payload에 reason/meta(정확도/상승확률)가 없을 수 있다.
        # 프론트 그리드에서 항상 보이도록 stock_analysis_results 최신값으로 best-effort 보강.
        #
        # 주의: stock_analysis_results 의 key는 ticker가 아니라 Stock(한글 종목명)일 수 있어
        # order_history.stock_name 우선, 없으면 ticker로 best-effort 조회한다.
        for r in rows:
            payload = r.get("payload")
            if not isinstance(payload, dict):
                payload = {}
                r["payload"] = payload

            # 이미 meta가 있으면 보강하지 않는다.
            if isinstance(payload.get("meta"), dict):
                continue

            stock_name = (r.get("stock_name") or "").strip()
            ticker = (r.get("ticker") or "").strip()
            if not stock_name and not ticker:
                continue

            try:
                q = supabase.table("stock_analysis_results").select(
                    '"Accuracy (%)","Rise Probability (%)","Recommendation","Analysis","Last Actual Price","Predicted Future Price","created_at"'
                )
                if stock_name:
                    q = q.eq("Stock", stock_name)
                else:
                    # fallback: Stock 컬럼이 ticker를 갖는 환경도 있을 수 있어 best-effort
                    q = q.eq("Stock", ticker)
                sresp = q.order("created_at", desc=True).limit(1).execute()
                srow = (sresp.data or [None])[0]
                if not isinstance(srow, dict):
                    continue

                payload["meta"] = {
                    "accuracy": srow.get("Accuracy (%)"),
                    "rise_probability": srow.get("Rise Probability (%)"),
                    "recommendation": srow.get("Recommendation"),
                    "analysis": srow.get("Analysis"),
                    "last_price": srow.get("Last Actual Price"),
                    "predicted_price": srow.get("Predicted Future Price"),
                    "analysis_created_at": srow.get("created_at"),
                }

                # reason 이 없으면 보강한 근거 타입이라도 넣어준다.
                if not isinstance(payload.get("reason"), str) or not str(payload.get("reason") or "").strip():
                    payload["reason"] = "enriched_from_stock_analysis_results(latest)"
            except Exception:
                # 보강 실패는 무시하고 원본만 반환한다.
                continue

        return rows
    except Exception as e:
        logger.error("order_history DB 조회 오류: %s", e)
        return []


def sync_open_orders_to_db(days: int = 7) -> bool:
    """KIS 미체결(주문잔량) → Supabase open_orders 테이블 동기화."""
    try:
        rows: list[dict] = []

        if settings.KIS_USE_MOCK:
            kst = pytz.timezone("Asia/Seoul")
            today = datetime.now(kst)
            start = (today - timedelta(days=max(1, days))).strftime("%Y%m%d")
            end = today.strftime("%Y%m%d")
            params = {
                "CANO": settings.KIS_CANO,
                "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                "OVRS_EXCG_CD": "NASD",
                "SORT_SQN": "DS",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
                "INQR_ST_DT": start,
                "INQR_END_DT": end,
            }
            result = get_overseas_order_detail(params, only_unfilled_pending=True)
            output = result.get("output", []) if isinstance(result, dict) else []
            if isinstance(output, list):
                for item in output:
                    key = "|".join(
                        [
                            str(item.get("odno", "")),
                            str(item.get("ord_dt", "")),
                            str(item.get("ovrs_pdno", item.get("pdno", ""))),
                            str(item.get("nccs_qty", "")),
                        ]
                    )
                    rows.append(
                        {
                            "open_key": key,
                            "odno": item.get("odno", ""),
                            "ord_dt": item.get("ord_dt", ""),
                            "ticker": item.get("ovrs_pdno", item.get("pdno", "")) or "",
                            "exchange": item.get("ovrs_excg_cd", "") or "",
                            "raw": item,
                            "synced_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
        else:
            for ex in ("NASD", "NYSE", "AMEX"):
                params = {
                    "CANO": settings.KIS_CANO,
                    "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
                    "OVRS_EXCG_CD": ex,
                    "SORT_SQN": "DS",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": "",
                }
                result = get_overseas_nccs(params)
                output = result.get("output", []) if isinstance(result, dict) else []
                if isinstance(output, list):
                    for item in output:
                        key = "|".join(
                            [
                                str(item.get("odno", "")),
                                str(item.get("ord_dt", "")),
                                str(item.get("ovrs_pdno", "")),
                                str(item.get("nccs_qty", "")),
                            ]
                        )
                        rows.append(
                            {
                                "open_key": key,
                                "odno": item.get("odno", ""),
                                "ord_dt": item.get("ord_dt", ""),
                                "ticker": item.get("ovrs_pdno", "") or "",
                                "exchange": item.get("ovrs_excg_cd", "") or ex,
                                "raw": item,
                                "synced_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                time.sleep(0.25)

        if rows:
            supabase.table("open_orders").upsert(rows, on_conflict="open_key").execute()

        # stale 정리: 현재 미체결에 없는 키 제거
        existing = supabase.table("open_orders").select("open_key").execute()
        current_keys = {r["open_key"] for r in rows}
        stale = [r["open_key"] for r in (existing.data or []) if r["open_key"] not in current_keys]
        if stale:
            supabase.table("open_orders").delete().in_("open_key", stale).execute()

        logger.info("open_orders 동기화 완료: %d개", len(rows))
        return True
    except Exception as e:
        logger.error("open_orders 동기화 오류: %s", e)
        return False


def get_open_orders_from_db() -> list[dict]:
    """Supabase open_orders 테이블 → 미체결(주문잔량) 리스트 반환."""
    try:
        resp = supabase.table("open_orders").select("raw").order("ord_dt", desc=True).execute()
        return [r["raw"] for r in (resp.data or []) if r.get("raw")]
    except Exception as e:
        logger.error("open_orders DB 조회 오류: %s", e)
        return []


def _delete_all_rows(table: str, pk_col: str) -> int:
    """
    Supabase(PostgREST)에서 테이블 전체 삭제(best-effort).
    반환: 삭제 응답에서 확인 가능한 행 수(없으면 0)
    """
    try:
        # PostgREST는 filter가 없으면 delete를 막는 경우가 있어, 항상 참인 조건으로 전체 삭제
        try:
            resp = supabase.table(table).delete().neq(pk_col, "__never__").execute()
        except Exception:
            # bigint 등 숫자 PK인 경우 "__never__" 문자열 비교가 실패할 수 있어 숫자 센티널로 재시도
            resp = supabase.table(table).delete().neq(pk_col, -1).execute()
        data = resp.data or []
        return len(data) if isinstance(data, list) else 0
    except Exception as e:
        logger.warning("%s 전체 삭제 실패: %s", table, e)
        return 0


def _delete_all_rows_status(table: str, pk_col: str) -> dict:
    """_delete_all_rows + 성공 여부/에러 메시지를 함께 반환."""
    try:
        try:
            resp = supabase.table(table).delete().neq(pk_col, "__never__").execute()
        except Exception:
            # bigint 등 숫자 PK인 경우 "__never__" 문자열 비교가 실패할 수 있어 숫자 센티널로 재시도
            resp = supabase.table(table).delete().neq(pk_col, -1).execute()
        data = resp.data or []
        deleted = len(data) if isinstance(data, list) else 0
        return {"ok": True, "deleted": deleted, "error": None}
    except Exception as e:
        msg = str(e)
        logger.warning("%s 전체 삭제 실패: %s", table, msg)
        return {"ok": False, "deleted": 0, "error": msg}


def _best_effort_usdkrw() -> float | None:
    """KIS psamount의 exrt(환율) 반환. 실패 시 None."""
    try:
        _, exrt = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd="NASD")
        return exrt if exrt and exrt > 0 else None
    except Exception:
        return None


def reset_trading_state_in_db(*, wipe_trade_logs: bool = False) -> dict:
    """
    '거래 상태'만 초기화한다.
    - 잔고/요약(holdings/holdings_summary)
    - 체결(order_fills)
    - 미체결(open_orders)
    - 주문 이력(order_history), 잔고 스냅샷(balance_snapshots)
    - 대시보드 그래프 스냅샷(equity_snapshots)

    초기 시드 자금은 KIS psamount(주문가능금액)에서 직접 조회한다.
    경제/추론/감성 테이블은 유지한다.
    """
    summary: dict = {}

    # 1) 스냅샷/거래 테이블 비우기
    deletions = {
        "holdings": _delete_all_rows_status("holdings", "ticker"),
        "holdings_summary": _delete_all_rows_status("holdings_summary", "id"),
        "order_fills": _delete_all_rows_status("order_fills", "fill_key"),
        "open_orders": _delete_all_rows_status("open_orders", "open_key"),
        "order_history": _delete_all_rows_status("order_history", "id"),
        "balance_snapshots": _delete_all_rows_status("balance_snapshots", "id"),
        "equity_snapshots": _delete_all_rows_status("equity_snapshots", "snapshot_key"),
    }

    # 1-1) (선택) 매매 실행 로그도 초기화에 포함
    #
    # - daily_buy_logs/daily_buy_items: 자동/수동 매수 실행 로그
    # - scheduler_minute_logs/scheduler_minute_items: 1분 매도 실행 로그
    # 운영/감사용으로 남길 수도 있어 기본은 False, "처음부터 다시 시작" 초기화에서는 True가 자연스럽다.
    if wipe_trade_logs:
        deletions.update(
            {
                "daily_buy_items": _delete_all_rows_status("daily_buy_items", "id"),
                "daily_buy_logs": _delete_all_rows_status("daily_buy_logs", "id"),
                "scheduler_minute_items": _delete_all_rows_status("scheduler_minute_items", "id"),
                "scheduler_minute_logs": _delete_all_rows_status("scheduler_minute_logs", "id"),
            }
        )
        summary["wipe_trade_logs"] = True
    else:
        summary["wipe_trade_logs"] = False
    summary["deleted"] = {k: v.get("deleted", 0) for k, v in deletions.items()}
    summary["delete_status"] = deletions

    # 2) 초기 자금 — KIS psamount에서 직접 조회 (USD + 환율)
    cash_usd, exrt = _get_cash_usd_via_psamount_best_effort(ovrs_excg_cd="NASD")
    summary["kis_cash_usd"] = cash_usd
    summary["kis_usdkrw_exrt"] = exrt

    if cash_usd is None or cash_usd <= 0:
        logger.warning("KIS psamount 조회 실패 또는 잔고 0 — holdings_summary.cash_usd 시드 스킵")
        summary["holdings_summary_seeded"] = False
    else:
        try:
            supabase.table("holdings_summary").upsert(
                {
                    "id": "main",
                    "cash_usd": float(cash_usd),
                    "initial_cash_usd": float(cash_usd),
                    "output2": {
                        "cash_source": "psamount",
                        "usdkrw_exrt": exrt,
                    },
                    "synced_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="id",
            ).execute()
            summary["holdings_summary_seeded"] = True
        except Exception as e:
            logger.warning("holdings_summary 초기 시드 실패: %s", e, exc_info=True)
            summary["holdings_summary_seeded"] = False

    # 3) 전체 성공 여부(테이블 삭제가 일부 실패해도 초기화는 계속되지만, 표시용으로 노출)
    delete_ok = all(bool(v.get("ok")) for v in deletions.values())
    seed_ok = bool(summary.get("holdings_summary_seeded"))
    summary["ok"] = bool(delete_ok and seed_ok)
    summary["delete_ok"] = bool(delete_ok)
    summary["seed_ok"] = bool(seed_ok)

    return summary
    