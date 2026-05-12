"""
주식 예측·티커 조회 API.

Supabase `stock_analysis_results` 에서 예측 목록·티커별 최신 행을 반환한다.
"""

# ─── 모듈 임포트 ───
from typing import List

from fastapi import APIRouter, HTTPException

from app.db.supabase import supabase
from app.schemas.stock import StockPrediction

router = APIRouter()

# ─── 상수 정의 ───

TICKER_TO_STOCK = {
    "NVDA": "엔비디아",
    "GOOGL": "구글 A",
    "AAPL": "애플",
    "MSFT": "마이크로소프트",
    "AMZN": "아마존",
    "AVGO": "브로드컴",
    "META": "메타",
    "TSLA": "테슬라",
    "WMT": "월마트",
    "MU": "마이크론",
    "AMD": "AMD",
    "ASML": "ASML",
    "INTC": "인텔",
    "COST": "코스트코",
    "NFLX": "넷플릭스",
    "CSCO": "시스코",
    "PLTR": "팔란티어",
    "LRCX": "램리서치",
    "AMAT": "어플라이드 머티리얼즈",
    "TXN": "텍사스 인스트루먼트",
    "LIN": "린드",
    "KLAC": "KLA Corp",
    "ARM": "Arm",
    "PEP": "펩시코",
    "TMUS": "티모바일",
    "ADI": "아나로그디바이스",
    "SNDK": "샌디스크",
    "QCOM": "퀄컴",
    "AMGN": "암젠",
    "SHOP": "쇼피파이",
    "STX": "씨게이트",
    "ISRG": "인튜이티브 서지컬",
    "APP": "앱러빈",
    "PANW": "팔로알토 네트웍스",
    "MRVL": "마벨 테크놀로지",
    "BKNG": "부킹홀딩스",
    "SBUX": "스타벅스",
    "CEG": "콘스텔레이션 에너지",
    "INTU": "인튜이트",
    "VRTX": "버텍스 파마슈티컬스",
    "ADBE": "어도비",
    "CMCSA": "컴캐스트",
    "CDNS": "케이던스",
    "SNPS": "시놉시스",
    "MAR": "메리어트",
    "MELI": "메르카도리브레",
    "ADP": "ADP",
    "ABNB": "에어비앤비",
    "MDLZ": "몬델리즈",
}

# ─── 엔드포인트 핸들러 ───


@router.get("/predictions", summary="주식 예측 결과 조회", response_model=List[StockPrediction])
def read_predictions():
    try:
        response = (
            supabase.table("stock_analysis_results")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        if not response.data:
            return []
        seen = {}
        for row in response.data:
            stock = row["Stock"]
            if stock not in seen:
                seen[stock] = row
        predictions = [
            StockPrediction(
                stock=row["Stock"],
                accuracy=row.get("Accuracy (%)"),
                last_price=row["Last Actual Price"],
                predicted_price=row["Predicted Future Price"],
                rise_probability=row["Rise Probability (%)"],
                recommendation=row["Recommendation"],
                analysis=row.get("Analysis"),
            )
            for row in seen.values()
        ]
        return predictions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예측 결과 조회 중 오류 발생: {str(e)}")


@router.get("/{ticker}", summary="특정 주식 정보 조회")
def read_stock_info(ticker: str):
    try:
        stock_name = TICKER_TO_STOCK.get(ticker.upper())
        if not stock_name:
            raise HTTPException(status_code=404, detail=f"지원하지 않는 티커: {ticker}")
        response = (
            supabase.table("stock_analysis_results")
            .select("*")
            .eq("Stock", stock_name)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail=f"{ticker} 분석 데이터를 찾을 수 없습니다.")
        return response.data[0]
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주식 정보 조회 중 오류 발생: {str(e)}")
