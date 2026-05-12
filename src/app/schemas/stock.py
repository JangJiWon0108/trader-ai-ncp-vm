"""
주식 분석·갱신 API용 Pydantic 모델.

예측 행 표현(StockPrediction)과 배치 갱신 응답(UpdateResponse)만 정의한다.
"""

# ─── 모듈 임포트 ───
from typing import Optional

from pydantic import BaseModel

# ─── 스키마 정의 ───


class StockPrediction(BaseModel):
    stock: str
    # Supabase 원천 컬럼이 NULL일 수 있어 프론트 타입(Nullable)과 정합을 맞춘다.
    accuracy: Optional[float] = None
    last_price: Optional[float] = None
    predicted_price: Optional[float] = None
    rise_probability: Optional[float] = None
    recommendation: Optional[str] = None
    analysis: Optional[str] = None


class UpdateResponse(BaseModel):
    success: bool
    message: str
    total_records: int = 0
    updated_records: int = 0
