"""
개발용 ASGI 실행 스크립트. `uvicorn app.main:app` 과 동일 역할.
"""

import os

import uvicorn
from uvicorn.config import LOG_LEVELS

if __name__ == "__main__":
    _lvl = (os.getenv("LOG_LEVEL") or "info").strip().lower()
    if _lvl not in LOG_LEVELS:
        _lvl = "info"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=_lvl,
        log_config=None,
    )
