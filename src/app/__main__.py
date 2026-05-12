"""
백엔드 실행 진입점.

목표: 긴 uvicorn 커맨드 대신 아래처럼 실행

  uv run backend
  uv run python -m app
"""

from __future__ import annotations

import os

import uvicorn
from uvicorn.config import LOG_LEVELS


def main() -> None:
    host = (os.getenv("BACKEND_HOST") or os.getenv("HOST") or "0.0.0.0").strip()
    port = int(os.getenv("BACKEND_PORT") or os.getenv("PORT") or "8000")
    reload_flag = (os.getenv("BACKEND_RELOAD") or os.getenv("RELOAD") or "true").strip().lower()
    reload_enabled = reload_flag in ("1", "true", "yes", "y", "on")

    _lvl = (os.getenv("LOG_LEVEL") or "info").strip().lower()
    if _lvl not in LOG_LEVELS:
        _lvl = "info"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level=_lvl,
        log_config=None,
    )


if __name__ == "__main__":
    main()

