"""
중앙 APIRouter: 잔고·경제·주식·추천 라우터를 prefix·tags 와 함께 등록한다.
"""

# ─── 모듈 임포트 ───
from fastapi import APIRouter

from app.api.routes.balance import router as balance_router
from app.api.routes.admin import router as admin_router
from app.api.routes.economic import router as economic_router
from app.api.routes.stock_recommendations import router as stock_recommendations_router
from app.api.routes.stocks import router as stocks_router
from app.api.routes.metrics import router as metrics_router

# ─── 라우터 등록 ───

api_router = APIRouter()
api_router.include_router(stock_recommendations_router, prefix="/stocks/recommendations", tags=["주식 추천"])
api_router.include_router(economic_router, prefix="/economic", tags=["경제 지표"])
api_router.include_router(balance_router, prefix="/balance", tags=["잔고"])
api_router.include_router(stocks_router, prefix="/stocks", tags=["주식"])
api_router.include_router(admin_router, prefix="/admin", tags=["관리자"])
api_router.include_router(metrics_router, prefix="/metrics", tags=["메트릭"])
