"""
추천·기술·감성·매도 후보 로직 및 Supabase 반영.

`stock_analysis_results`, `stock_recommendations`, `ticker_sentiment_analysis` 등을 조회·갱신한다.
"""

# ─── 모듈 임포트 ───
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
import requests
from requests import RequestException

from app.core.config import settings
from app.db.supabase import supabase
from app.services.balance_service import get_overseas_balance
from app.utils.logger import get_logger

logger = get_logger(__name__)

_HTTP_TIMEOUT = (5.0, 30.0)  # (connect, read) seconds


def has_today_sentiment_data_kst() -> bool:
    """오늘(KST) 감성 데이터가 이미 존재하면 True — Alpha Vantage 일일 호출 제한 보호용."""
    try:
        resp = (
            supabase.table("ticker_sentiment_analysis")
            .select("calculation_date")
            .order("calculation_date", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return False
        raw = (rows[0] or {}).get("calculation_date")
        if not raw:
            return False
        kst = pytz.timezone("Asia/Seoul")
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        today_kst = datetime.now(kst).date()
        return dt.astimezone(kst).date() == today_kst
    except Exception:
        return True  # 판단 불가 시 안전하게 "있다"로 간주 → 호출 차단


# ─── 상수 정의 ───

STOCK_TO_TICKER = {
    "엔비디아": "NVDA",
    "구글 A": "GOOGL",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "아마존": "AMZN",
    "브로드컴": "AVGO",
    "메타": "META",
    "테슬라": "TSLA",
    "월마트": "WMT",
    "마이크론": "MU",
    "AMD": "AMD",
    "ASML": "ASML",
    "인텔": "INTC",
    "코스트코": "COST",
    "넷플릭스": "NFLX",
    "시스코": "CSCO",
    "팔란티어": "PLTR",
    "램리서치": "LRCX",
    "어플라이드 머티리얼즈": "AMAT",
    "텍사스 인스트루먼트": "TXN",
    "린드": "LIN",
    "KLA Corp": "KLAC",
    "Arm": "ARM",
    "펩시코": "PEP",
    "티모바일": "TMUS",
    "아나로그디바이스": "ADI",
    "샌디스크": "SNDK",
    "퀄컴": "QCOM",
    "암젠": "AMGN",
    "쇼피파이": "SHOP",
    "씨게이트": "STX",
    "인튜이티브 서지컬": "ISRG",
    "앱러빈": "APP",
    "팔로알토 네트웍스": "PANW",
    "마벨 테크놀로지": "MRVL",
    "부킹홀딩스": "BKNG",
    "스타벅스": "SBUX",
    "콘스텔레이션 에너지": "CEG",
    "인튜이트": "INTU",
    "버텍스 파마슈티컬스": "VRTX",
    "어도비": "ADBE",
    "컴캐스트": "CMCSA",
    "케이던스": "CDNS",
    "시놉시스": "SNPS",
    "메리어트": "MAR",
    "메르카도리브레": "MELI",
    "ADP": "ADP",
    "에어비앤비": "ABNB",
    "몬델리즈": "MDLZ",
}


# ─── 공개 API ───


class StockRecommendationService:
    def __init__(self):
        self.stock_columns = list(STOCK_TO_TICKER.keys())
        self.lookback_days = settings.TECH_LOOKBACK_DAYS

    def calculate_sma(self, series, period):
        return series.rolling(window=period).mean()

    def calculate_ema(self, series, period):
        return series.ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, series, period=None):
        period = period or settings.TECH_RSI_PERIOD
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def calculate_macd(self, series, short_period=None, long_period=None, signal_period=None):
        short_period = short_period or settings.TECH_MACD_SHORT
        long_period = long_period or settings.TECH_MACD_LONG
        signal_period = signal_period or settings.TECH_MACD_SIGNAL
        short_ema = self.calculate_ema(series, short_period)
        long_ema = self.calculate_ema(series, long_period)
        macd = short_ema - long_ema
        signal = self.calculate_ema(macd, signal_period)
        return macd, signal

    def generate_technical_recommendations(self):
        """기술적 지표를 기반으로 추천 데이터를 생성하고 Supabase에 저장"""
        # 최근 6개월 데이터만 가져오기 (경제·주가 일자 컬럼과 맞추기 위해 KST 달력 기준)
        kst = pytz.timezone("Asia/Seoul")
        end_date = datetime.now(kst)
        start_date = end_date - timedelta(days=self.lookback_days)
        start_date_str = start_date.strftime("%Y-%m-%d")

        # Supabase 쿼리에서 컬럼명에 큰따옴표 추가
        quoted_columns = [f'"{col}"' for col in self.stock_columns]
        quoted_columns.append('"날짜"')  # 날짜 컬럼 추가

        response = supabase.table("economic_and_stock_data") \
            .select(*quoted_columns) \
            .gte("날짜", start_date_str) \
            .order("날짜") \
            .execute()

        if not response.data:
            return {"message": "데이터가 없습니다", "data": []}

        # 데이터프레임 생성 (컬럼명은 큰따옴표 제외)
        df = pd.DataFrame(response.data)
        df["날짜"] = pd.to_datetime(df["날짜"])
        df.set_index("날짜", inplace=True)
        df = df.astype(float)

        recommendations = []
        for stock in self.stock_columns:
            prices = df[stock]

            sma20 = self.calculate_sma(prices, settings.TECH_SMA_SHORT)
            sma50 = self.calculate_sma(prices, settings.TECH_SMA_LONG)
            golden_cross = sma20 > sma50
            rsi = self.calculate_rsi(prices)
            macd, signal = self.calculate_macd(prices)
            macd_buy_signal = macd > signal
            recommended = golden_cross & (rsi < settings.BUY_RSI_MAX) & macd_buy_signal

            # 가장 최근 날짜의 결과만 저장
            latest_date = df.index[-1]
            if all(pd.notna([sma20[latest_date], sma50[latest_date], rsi[latest_date], macd[latest_date], signal[latest_date]])):
                recommendations.append({
                    "날짜": latest_date.strftime("%Y-%m-%d"),
                    "종목": stock,
                    "SMA20": float(sma20[latest_date]),
                    "SMA50": float(sma50[latest_date]),
                    "골든_크로스": bool(golden_cross[latest_date]),
                    "RSI": float(rsi[latest_date]),
                    "MACD": float(macd[latest_date]),
                    "Signal": float(signal[latest_date]),
                    "MACD_매수_신호": bool(macd_buy_signal[latest_date]),
                    "추천_여부": bool(recommended[latest_date])
                })

        # 기존 데이터 삭제 후 새 데이터 저장
        try:
            # 전체 데이터 삭제 (항상 TRUE인 조건 사용)
            supabase.table("stock_recommendations").delete().eq("날짜", "1900-01-01").gte("날짜", "1900-01-01").execute()
            
            # 또는 이런 방식도 가능합니다 (모든 레코드와 매치되는 조건)
            supabase.table("stock_recommendations").delete().gte("날짜", "1900-01-01").execute()
            
            # 새 데이터 삽입
            supabase.table("stock_recommendations").insert(recommendations).execute()
        
        except Exception as e:
            logger.exception("추천 데이터 DB 저장 실패: %s", e)
            raise Exception(f"추천 주식 분석 중 오류: {str(e)}")

        return {"message": f"{len(recommendations)}개의 추천 데이터가 생성되었습니다", "data": recommendations}

    def get_stock_recommendations(self):
        """
        Accuracy가 70% 이상이고 상승 확률이 3% 이상인 추천 주식 목록을 반환합니다.
        상승 확률 기준으로 내림차순 정렬됩니다.
        """
        response = supabase.table("stock_analysis_results").select("*").order("created_at", desc=True).execute()
        if not response.data:
            return {"message": "분석 결과를 찾을 수 없습니다", "recommendations": []}

        df = pd.DataFrame(response.data)
        numeric_columns = ['Accuracy (%)', 'Rise Probability (%)']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        filtered_df = df[(df['Accuracy (%)'] >= settings.BUY_MODEL_ACCURACY_MIN) & (df['Rise Probability (%)'] >= settings.BUY_RISE_PROB_MIN)]
        filtered_df = filtered_df.sort_values(by='Rise Probability (%)', ascending=False)
        result_columns = [
            'Stock', 'Accuracy (%)', 'Rise Probability (%)', 'Last Actual Price',
            'Predicted Future Price', 'Recommendation', 'Analysis'
        ]
        result_df = filtered_df[result_columns]

        recommendations = result_df.to_dict(orient='records')
        return {
            "message": f"{len(recommendations)}개의 추천 주식을 찾았습니다",
            "recommendations": recommendations
        }

    def get_recommendations_with_sentiment(self):
        """
        get_stock_recommendations에서 가져온 추천 주식 중 
        ticker_sentiment_analysis 테이블에서 average_sentiment_score >= 0.15인 주식만 필터링하고,
        두 데이터 소스의 정보를 결합하여 반환합니다.
        """
        stock_recs = self.get_stock_recommendations()
        recommendations = stock_recs.get("recommendations", [])
        if not recommendations:
            return {"message": "추천 주식이 없습니다", "results": []}

        sentiment_response = supabase.table("ticker_sentiment_analysis").select("*").gte("average_sentiment_score", settings.BUY_SENTIMENT_MIN).execute()
        if not sentiment_response.data:
            return {"message": "감정 분석 데이터가 없습니다", "results": []}

        ticker_to_recommendation = {
            STOCK_TO_TICKER.get(rec["Stock"]): rec 
            for rec in recommendations 
            if rec["Stock"] in STOCK_TO_TICKER
        }
        sentiment_data = {item["ticker"]: item for item in sentiment_response.data}

        results = []
        for ticker, sentiment in sentiment_data.items():
            if ticker in ticker_to_recommendation:
                recommendation = ticker_to_recommendation[ticker]
                combined_data = {
                    "ticker": ticker,
                    "stock_name": recommendation["Stock"],
                    "accuracy": recommendation["Accuracy (%)"],
                    "rise_probability": recommendation["Rise Probability (%)"],
                    "last_actual_price": recommendation["Last Actual Price"],
                    "predicted_future_price": recommendation["Predicted Future Price"],
                    "recommendation": recommendation["Recommendation"],
                    "analysis": recommendation["Analysis"],
                    "average_sentiment_score": sentiment["average_sentiment_score"],
                    "article_count": sentiment["article_count"],
                    "calculation_date": sentiment["calculation_date"]
                }
                results.append(combined_data)

        return {
            "message": f"{len(results)}개의 추천 주식을 분석했습니다",
            "results": results
        }

    def fetch_and_store_sentiment_for_recommendations(self):
        """
        추천 주식과 보유 중인 주식에 대해 뉴스 감정 데이터를 가져오고, Supabase에 저장하며,
        감정 분석과 추천 정보를 통합하여 반환합니다.
        """
        # 추천 주식 목록 가져오기
        stock_recs = self.get_stock_recommendations()
        recommendations = stock_recs.get("recommendations", [])
        
        # 추천 주식의 티커 목록 생성
        recommended_tickers = [STOCK_TO_TICKER.get(rec["Stock"]) for rec in recommendations if rec["Stock"] in STOCK_TO_TICKER]
        
        # 보유 주식 정보 가져오기
        balance_result = get_overseas_balance()
        holdings = []
        
        if balance_result.get("rt_cd") == "0" and "output1" in balance_result:
            holdings = balance_result.get("output1", [])
            logger.info(f"보유 주식 정보를 성공적으로 가져왔습니다. 총 {len(holdings)}개 종목 보유 중")
        else:
            logger.info(f"보유 주식 정보를 가져오는데 실패했습니다: {balance_result.get('msg1', '알 수 없는 오류')}")
        
        # 보유 주식의 티커 목록 생성
        holding_tickers = [item.get("ovrs_pdno") for item in holdings if item.get("ovrs_pdno")]
        
        # 추천 주식과 보유 주식의 티커를 합치고 중복 제거
        all_tickers = list(set(recommended_tickers + holding_tickers))
        
        if not all_tickers:
            return {"message": "분석할 티커가 없습니다", "results": []}

        logger.info(f"분석할 티커 목록 ({len(all_tickers)}개): {all_tickers}")

        api_keys = [
            k.strip()
            for k in (
                settings.ALPHA_VANTAGE_API_KEY_MAIN,
                settings.ALPHA_VANTAGE_API_KEY_SUB_1,
                settings.ALPHA_VANTAGE_API_KEY_SUB_2,
            )
            if k and str(k).strip()
        ]

        if not api_keys:
            return {
                "message": "Alpha Vantage API 키가 없습니다 (ALPHA_VANTAGE_API_KEY_MAIN / SUB_1 / SUB_2)",
                "results": [],
            }

        kst = pytz.timezone("Asia/Seoul")
        relevance_threshold = settings.SENTIMENT_RELEVANCE_THRESHOLD
        sleep_interval = 5 if len(api_keys) == 1 else 15
        yesterday = (datetime.now(kst) - timedelta(days=settings.SENTIMENT_LOOKBACK_DAYS)).strftime("%Y%m%dT0000")

        base_url = "https://www.alphavantage.co/query"

        ticker_to_stock = {ticker: stock for stock, ticker in STOCK_TO_TICKER.items()}
        recommendations_by_ticker = {
            STOCK_TO_TICKER[rec["Stock"]]: rec for rec in recommendations if rec["Stock"] in STOCK_TO_TICKER
        }

        # 보유 주식 정보를 ticker로 매핑
        holdings_by_ticker = {item.get("ovrs_pdno"): item for item in holdings if item.get("ovrs_pdno")}

        # 오늘(KST) 이미 적재되어 있으면 스킵 (일반적 동작)
        today_kst = datetime.now(kst).date().isoformat()
        try:
            exists = (
                supabase.table("ticker_sentiment_analysis")
                .select("ticker", count="exact")
                .eq("date_kst", today_kst)
                .limit(1)
                .execute()
            )
            if (exists.count or 0) > 0:
                logger.info("감성 데이터(%s) 이미 존재 — 스킵", today_kst)
                return {
                    "skipped": True,
                    "date_kst": today_kst,
                    "message": f"감성 데이터({today_kst})가 이미 적재되어 있어 스킵했습니다.",
                    "results": [],
                }
        except Exception as e:
            # 스킵 체크 실패해도 적재는 진행(안전)
            logger.warning("감성 스킵 체크 실패 — 계속 진행: %s", e, exc_info=True)

        results = []
        results_lock = threading.Lock()

        def fetch_group(group_tickers, api_key):
            for ticker in group_tickers:
                logger.info(f"{ticker} 처리 중... (키: {api_key[:6]}...)")
                params = {
                    "function": "NEWS_SENTIMENT",
                    "time_from": yesterday,
                    "limit": 100,
                    "apikey": api_key,
                    "tickers": ticker,
                }

                try:
                    response = requests.get(base_url, params=params, timeout=_HTTP_TIMEOUT)
                except RequestException as re:
                    with results_lock:
                        results.append({
                            "ticker": ticker,
                            "stock_name": ticker_to_stock.get(ticker, ticker),
                            "message": f"API 호출 실패: {str(re)}",
                            "is_recommended": ticker in recommended_tickers,
                            "is_holding": ticker in holding_tickers,
                            "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                            "holding_info": holdings_by_ticker.get(ticker, {})
                        })
                    time.sleep(sleep_interval)
                    continue
                except Exception as re:
                    with results_lock:
                        results.append({
                            "ticker": ticker,
                            "stock_name": ticker_to_stock.get(ticker, ticker),
                            "message": f"API 호출 실패: {str(re)}",
                            "is_recommended": ticker in recommended_tickers,
                            "is_holding": ticker in holding_tickers,
                            "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                            "holding_info": holdings_by_ticker.get(ticker, {})
                        })
                    time.sleep(sleep_interval)
                    continue

                if response.status_code != 200:
                    with results_lock:
                        results.append({
                            "ticker": ticker,
                            "stock_name": ticker_to_stock.get(ticker, ticker),
                            "message": f"API 호출 실패(HTTP {response.status_code})",
                            "is_recommended": ticker in recommended_tickers,
                            "is_holding": ticker in holding_tickers,
                            "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                            "holding_info": holdings_by_ticker.get(ticker, {})
                        })
                    time.sleep(sleep_interval)
                    continue

                api_data = response.json()
                feed = api_data.get('feed', [])

                articles = [
                    float(sentiment['ticker_sentiment_score'])
                    for article in feed
                    for sentiment in article.get('ticker_sentiment', [])
                    if sentiment['ticker'] == ticker and float(sentiment['relevance_score']) >= relevance_threshold
                ]

                if not articles:
                    with results_lock:
                        results.append({
                            "ticker": ticker,
                            "stock_name": ticker_to_stock.get(ticker, ticker),
                            "message": "관련 기사 없음",
                            "is_recommended": ticker in recommended_tickers,
                            "is_holding": ticker in holding_tickers,
                            "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                            "holding_info": holdings_by_ticker.get(ticker, {})
                        })
                    time.sleep(sleep_interval)
                    continue

                average_sentiment = sum(articles) / len(articles)
                article_count = len(articles)
                # KST 기준 날짜/시각을 명시적으로 저장
                now_kst = datetime.now(kst)
                calculation_date = now_kst.isoformat()
                date_kst = now_kst.date().isoformat()

                supabase_data = {
                    "ticker": ticker,
                    "average_sentiment_score": average_sentiment,
                    "article_count": article_count,
                    "calculation_date": calculation_date,
                    "date_kst": date_kst,
                }
                # 일별 누적: (date_kst, ticker) 유니크 키 기반 upsert
                supabase.table("ticker_sentiment_analysis").upsert(
                    supabase_data,
                    on_conflict="date_kst,ticker",
                ).execute()

                with results_lock:
                    results.append({
                        "ticker": ticker,
                        "stock_name": ticker_to_stock.get(ticker, ticker),
                        "average_sentiment_score": average_sentiment,
                        "article_count": article_count,
                        "is_recommended": ticker in recommended_tickers,
                        "is_holding": ticker in holding_tickers,
                        "recommendation_info": recommendations_by_ticker.get(ticker, {}),
                        "holding_info": holdings_by_ticker.get(ticker, {})
                    })
                time.sleep(sleep_interval)

        # 티커를 키 수만큼 균등 분배 후 병렬 실행
        groups = [all_tickers[i::len(api_keys)] for i in range(len(api_keys))]
        threads = [
            threading.Thread(target=fetch_group, args=(group, key))
            for group, key in zip(groups, api_keys)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        return {
            "message": f"{len(results)}개의 티커(추천 주식: {len(recommended_tickers)}개, 보유 주식: {len(holding_tickers)}개)를 분석했습니다",
            "results": results
        }

    def get_combined_recommendations_with_technical_and_sentiment(self):
        """
        추천 주식 목록을 기술적 지표(stock_recommendations 테이블)와 감정 분석(ticker_sentiment_analysis 테이블)을
        결합하여 반환합니다.
        - stock_recommendations에서 골든_크로스=true, MACD_매수_신호=true, RSI<50 중 하나 이상 만족하는 종목 필터링
        - ticker_sentiment_analysis에서 average_sentiment_score >= 0.15인 데이터와 결합
        - get_stock_recommendations의 결과와 통합하여 반환
        - 추가 조건: sentiment_score와 기술적 지표를 기반으로 매수 추천 필터링
        """
        try:
            # 1. 기술적 지표 데이터 조회
            tech_response = supabase.table("stock_recommendations").select("*").order("날짜", desc=True).execute()
            if not tech_response.data:
                return {"message": "기술적 지표 데이터가 없습니다", "results": []}
            
            tech_df = pd.DataFrame(tech_response.data)
            
            # 데이터 타입 변환
            tech_df["골든_크로스"] = tech_df["골든_크로스"].astype(bool)
            tech_df["MACD_매수_신호"] = tech_df["MACD_매수_신호"].astype(bool)
            tech_df["RSI"] = pd.to_numeric(tech_df["RSI"])
            
            # 필터링: 골든_크로스=true, MACD_매수_신호=true, RSI<BUY_RSI_MAX 중 하나 이상 (OR)
            mask_golden = tech_df["골든_크로스"] == True
            mask_macd = tech_df["MACD_매수_신호"] == True
            mask_rsi = tech_df["RSI"] < settings.BUY_RSI_MAX
            combined_mask = np.logical_or.reduce([mask_golden, mask_macd, mask_rsi])
            filtered_tech_df = tech_df[combined_mask]
            
            if filtered_tech_df.empty:
                return {"message": "조건을 만족하는 기술적 지표가 없습니다", "results": []}
            
            # 2. 주가 예측 데이터 조회
            stock_recs = self.get_stock_recommendations()
            recommendations = stock_recs.get("recommendations", [])
            if not recommendations:
                return {"message": "추천 주식이 없습니다", "results": []}
            
            # 3. 감정 분석 데이터 조회
            sentiment_response = supabase.table("ticker_sentiment_analysis").select("*").gte("average_sentiment_score", settings.BUY_SENTIMENT_MIN).execute()
            
            # 4. 데이터 매핑 준비
            tech_map = {row["종목"]: row.to_dict() for _, row in filtered_tech_df.iterrows()}
            sentiment_map = {item["ticker"]: item for item in sentiment_response.data} if sentiment_response.data else {}
            
            # 5. 결과 통합
            results = []
            for rec in recommendations:
                stock_name = rec["Stock"]
                if stock_name not in STOCK_TO_TICKER:
                    continue
                
                ticker = STOCK_TO_TICKER[stock_name]
                tech_data = tech_map.get(stock_name)
                if tech_data is None:
                    continue  # 기술적 지표가 없으면 제외
                
                sentiment = sentiment_map.get(ticker)
                
                # 통합 데이터 생성
                combined_data = {
                    "ticker": ticker,
                    "stock_name": stock_name,
                    "accuracy": rec["Accuracy (%)"],
                    "rise_probability": rec["Rise Probability (%)"],
                    "last_price": rec["Last Actual Price"],
                    "predicted_price": rec["Predicted Future Price"],
                    "recommendation": rec["Recommendation"],
                    "analysis": rec["Analysis"],
                    "sentiment_score": sentiment["average_sentiment_score"] if sentiment else None,
                    "article_count": sentiment["article_count"] if sentiment else None,
                    "sentiment_date": sentiment["calculation_date"] if sentiment else None,
                    "technical_date": tech_data["날짜"],
                    "sma20": float(tech_data["SMA20"]),
                    "sma50": float(tech_data["SMA50"]),
                    "golden_cross": bool(tech_data["골든_크로스"]),
                    "rsi": float(tech_data["RSI"]),
                    "macd": float(tech_data["MACD"]),
                    "signal": float(tech_data["Signal"]),
                    "macd_buy_signal": bool(tech_data["MACD_매수_신호"]),
                    "technical_recommended": bool(tech_data["추천_여부"])
                }
                results.append(combined_data)
            
            # 6. 매수 추천 조건에 따른 추가 필터링 후 순위 계산
            final_results = []
            for item in results:
                sentiment_score = item["sentiment_score"]
                tech_conditions = [item["golden_cross"], item["rsi"] < settings.BUY_RSI_MAX, item["macd_buy_signal"]]

                if sentiment_score is not None and sentiment_score >= settings.BUY_SENTIMENT_MIN:
                    if sum(tech_conditions) >= settings.BUY_TECH_MIN_WITH_SENTIMENT:
                        final_results.append(item)
                else:
                    if sum(tech_conditions) >= settings.BUY_TECH_MIN_WITHOUT_SENTIMENT:
                        final_results.append(item)

            # 7. 종합 점수 계산 및 정렬
            for item in final_results:
                sentiment_score = item["sentiment_score"] if item["sentiment_score"] is not None else 0.0
                tech_conditions_count = (
                    settings.BUY_SCORE_WEIGHT_GOLDEN_CROSS * item["golden_cross"] +
                    settings.BUY_SCORE_WEIGHT_RSI * (item["rsi"] < settings.BUY_RSI_MAX) +
                    settings.BUY_SCORE_WEIGHT_MACD * item["macd_buy_signal"]
                )
                item["composite_score"] = (
                    settings.BUY_SCORE_WEIGHT_RISE_PROB * item["rise_probability"] +
                    settings.BUY_SCORE_WEIGHT_TECH * tech_conditions_count +
                    settings.BUY_SCORE_WEIGHT_SENTIMENT * sentiment_score
                )

            final_results.sort(key=lambda x: x["composite_score"], reverse=True)

            # 8. 결과 반환
            return {
                "message": f"{len(final_results)}개의 매수 추천 주식을 찾았습니다",
                "results": final_results
            }
        
        except Exception as e:
            logger.exception("기술·감성 결합 추천 처리 실패: %s", e)
            raise Exception(f"추천 주식 분석 중 오류: {str(e)}")

    def get_stocks_to_sell(self):
        """
        매도 대상 종목을 식별하는 함수
        
        매도 조건:
        1. 구매가 대비 현재가가 +5% 이상(익절) 또는 -7% 이하(손절)인 종목
        2. 감성 점수 < -0.15이고 기술적 지표 중 2개 이상 매도 신호인 종목
        3. 기술적 지표 중 3개 이상 매도 신호인 종목
        
        반환값:
        - sell_candidates: 매도 대상 종목 목록
        - technical_data: 종목별 기술적 지표 데이터
        - sentiment_data: 종목별 감성 분석 데이터
        """
        try:
            # 1. 보유 종목 정보 가져오기 (NASD/NYSE/AMEX 전 거래소)
            from app.services.balance_service import get_all_overseas_balances
            balance_result = get_all_overseas_balances()
            if balance_result.get("rt_cd") != "0" or "output1" not in balance_result:
                return {
                    "message": f"보유 종목 정보를 가져오는데 실패했습니다: {balance_result.get('msg1', '알 수 없는 오류')}",
                    "sell_candidates": []
                }
            
            holdings = balance_result.get("output1", [])
            if not holdings:
                return {
                    "message": "보유 종목이 없습니다",
                    "sell_candidates": []
                }
            
            logger.info(f"보유 종목 정보를 성공적으로 가져왔습니다. 총 {len(holdings)}개 종목 보유 중")
            
            # 2. 티커와 한글명 매핑 생성
            ticker_to_korean = {}
            korean_to_ticker = {}
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                name = item.get("ovrs_item_name")
                if ticker and name:
                    ticker_to_korean[ticker] = name
                    korean_to_ticker[name] = ticker
            
            # 3. 기술적 지표 데이터 가져오기
            tech_response = supabase.table("stock_recommendations").select("*").order("날짜", desc=True).execute()
            tech_data = pd.DataFrame(tech_response.data) if tech_response.data else pd.DataFrame()
            
            if not tech_data.empty:
                # 데이터 타입 변환
                tech_data["골든_크로스"] = tech_data["골든_크로스"].astype(bool)
                tech_data["MACD_매수_신호"] = tech_data["MACD_매수_신호"].astype(bool)
                tech_data["RSI"] = pd.to_numeric(tech_data["RSI"])
                
                # 최신 데이터만 필터링 (종목별 가장 최근 날짜의 데이터)
                tech_data = tech_data.sort_values("날짜", ascending=False)
                tech_data = tech_data.drop_duplicates(subset=["종목"], keep="first")
            
            # 4. 감성 분석 데이터 가져오기
            sentiment_response = supabase.table("ticker_sentiment_analysis").select("*").execute()
            sentiment_data = {item["ticker"]: item for item in sentiment_response.data} if sentiment_response.data else {}
            
            # 5. 매도 대상 종목 식별
            sell_candidates = []
            
            for item in holdings:
                ticker = item.get("ovrs_pdno")
                stock_name = item.get("ovrs_item_name")
                purchase_price = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("now_pric2", 0))
                quantity = int(item.get("ovrs_cblc_qty", 0))
                qty_sellable = int(item.get("ord_psbl_qty", 0))
                exchange_code = item.get("ovrs_excg_cd", "")
                
                # 가격 변동률 계산
                price_change_percent = ((current_price - purchase_price) / purchase_price) * 100 if purchase_price > 0 else 0
                
                # 매도 근거와 신호 수를 추적할 변수들
                sell_reasons = []
                technical_sell_signals = 0
                
                # 조건 1: 가격 기반 매도 (익절/손절)
                if price_change_percent >= settings.SELL_TAKE_PROFIT_PCT:
                    sell_reasons.append(f"익절 조건 충족: 구매가 대비 {price_change_percent:.2f}% 상승")
                elif price_change_percent <= settings.SELL_STOP_LOSS_PCT:
                    sell_reasons.append(f"손절 조건 충족: 구매가 대비 {price_change_percent:.2f}% 하락")
                
                # 기술적 지표 확인
                tech_record = None
                if not tech_data.empty:
                    tech_filtered = tech_data[tech_data["종목"] == stock_name]
                    if not tech_filtered.empty:
                        tech_record = tech_filtered.iloc[0].to_dict()
                
                tech_sell_signals_details = []
                if tech_record:
                    # 기술적 지표 매도 신호 확인
                    if not tech_record["골든_크로스"]:
                        technical_sell_signals += 1
                        tech_sell_signals_details.append("데드 크로스")

                    if tech_record["RSI"] > settings.SELL_RSI_OVERBOUGHT:
                        technical_sell_signals += 1
                        tech_sell_signals_details.append(f"RSI 과매수({tech_record['RSI']:.2f})")
                    
                    if not tech_record["MACD_매수_신호"]:  # MACD 매수 신호가 없으면 매도 신호
                        technical_sell_signals += 1
                        tech_sell_signals_details.append("MACD 매도 신호")
                
                # 감성 분석 데이터 확인
                sentiment_score = None
                if ticker in sentiment_data:
                    sentiment_score = sentiment_data[ticker].get("average_sentiment_score")
                
                # ── 조건 2/3: 감성 유무에 따라 기술지표 임계값이 달라짐 ─────────────
                # 1) 감성 데이터 없음 → 기술지표 n개 이상이면 매도(보수적으로 완화)
                if sentiment_score is None:
                    if technical_sell_signals >= settings.SELL_TECH_MIN_WITHOUT_SENTIMENT:
                        sell_reasons.append(
                            f"감성 데이터 없음 + 기술적 매도 신호({technical_sell_signals}개): {', '.join(tech_sell_signals_details)}"
                        )
                else:
                    # 2) 감성이 충분히 부정적이면 더 낮은 기술 임계값으로 매도
                    if sentiment_score < settings.SELL_SENTIMENT_MAX and technical_sell_signals >= settings.SELL_TECH_MIN_WITH_SENTIMENT:
                        sell_reasons.append(
                            f"부정적 감성({sentiment_score:.2f})과 기술적 매도 신호({technical_sell_signals}개): {', '.join(tech_sell_signals_details)}"
                        )
                    # 3) 감성이 중립/긍정이더라도 기술이 충분히 나쁘면(tech-only) 매도
                    elif technical_sell_signals >= settings.SELL_TECH_MIN_TECH_ONLY:
                        sell_reasons.append(
                            f"기술적 매도 신호({technical_sell_signals}개): {', '.join(tech_sell_signals_details)}"
                        )
                
                # 매도 대상 판단
                if sell_reasons:
                    sell_candidates.append({
                        "ticker": ticker,
                        "stock_name": stock_name,
                        "purchase_price": purchase_price,
                        "current_price": current_price,
                        "price_change_percent": price_change_percent,
                        "quantity": quantity,
                        "qty_sellable": qty_sellable,
                        "exchange_code": exchange_code,
                        "sell_reasons": sell_reasons,
                        "technical_sell_signals": technical_sell_signals,
                        "technical_sell_details": tech_sell_signals_details if tech_sell_signals_details else None,
                        "sentiment_score": sentiment_score,
                        "technical_data": tech_record
                    })
            
            # 가격 변동률이 큰 순서로 정렬 (절대값 기준)
            sell_candidates.sort(key=lambda x: abs(x["price_change_percent"]), reverse=True)
            
            return {
                "message": f"{len(sell_candidates)}개의 매도 대상 종목을 식별했습니다",
                "sell_candidates": sell_candidates
            }
            
        except Exception as e:
            logger.exception("매도 대상 종목 식별 실패: %s", e)
            return {
                "message": f"매도 대상 종목 식별 중 오류 발생: {str(e)}",
                "sell_candidates": []
            }