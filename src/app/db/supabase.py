"""
Supabase 클라이언트 싱글톤.

서버 측 쓰기 시 RLS 우회를 위해 SERVICE_KEY 가 있으면 우선 사용하고,
없으면 일반 KEY 로 연결한다.
"""

# ─── 모듈 임포트 ───
from supabase import Client, create_client

from app.core.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── 클라이언트 생성 ───

url: str = settings.SUPABASE_URL
# service role: RLS 우회 — 서버 전용 쓰기에 사용
key: str = settings.SUPABASE_SERVICE_KEY or settings.SUPABASE_KEY
supabase: Client = create_client(url, key)


# ─── 공개 API ───


def get_data(table_name):
    """Supabase 테이블 전체 select. 실패 시 None."""
    try:
        response = supabase.table(table_name).select("*").execute()
        logger.info("%s 데이터 조회 성공", table_name)
        return response.data
    except Exception as e:
        logger.error("데이터 조회 오류 (%s): %s", table_name, e, exc_info=True)
        return None
