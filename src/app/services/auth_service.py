"""
KIS 토큰 만료 시각 등 문자열 → timezone-aware datetime 파싱.

`balance_service` 가 Supabase `access_tokens.expiration_time` 해석에 사용한다.
"""

# ─── 모듈 임포트 ───
import re
from datetime import datetime, timedelta

import pytz

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─── 공개 API ───


def parse_expiration_date(date_str):
    """ISO·KIS 형식 문자열 또는 datetime 을 UTC 기준 datetime 으로 정규화."""
    try:
        if isinstance(date_str, str) and re.search(r"\.\d{5}\+", date_str):
            date_str = re.sub(r"\.(\d{5})\+", r".\g<1>0+", date_str)

        if isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%f%z")
            except ValueError:
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    return dt.replace(tzinfo=pytz.UTC)
                except ValueError:
                    pass
        return date_str
    except Exception as e:
        logger.warning("날짜 파싱 오류: %s", e, exc_info=True)
        return datetime.now(pytz.UTC) + timedelta(days=1)
