"""
프로젝트 공용 로거.

- get_logger() 로만 로거를 얻어 사용한다.
- 기본은 stdout 로깅(쿠버네티스/도커 로그 수집 친화적).
- 파일 로깅은 옵션(LOG_TO_FILE=1)일 때만 활성화한다.
- 출력 포맷에만 [JJW] 접두가 붙는다(특정 로거만 남기는 필터가 아님).
- DEBUG·INFO 등 “모든 심각도”를 보려면 환경변수 LOG_LEVEL=DEBUG 처럼
  루트/핸들러 최소 레벨을 낮춘다(기본 INFO면 DEBUG 행은 출력·미러에 안 쌓임).
- 관리자 memory tail 은 기본적으로 터미널 stdout/stderr 미러(terminal_mirror).
  TERMINAL_LOG_MIRROR=0 이면 예전처럼 logging 전용 링버퍼만 사용한다.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock

_init_lock = Lock()
_initialized = False


class _RingBufferHandler(logging.Handler):
    """최근 로그를 메모리에 보관(관리자 tail용)."""

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self._buf: deque[str] = deque(maxlen=max(1, int(capacity)))
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            # 포맷 실패는 로깅 자체를 깨지 않게 한다.
            return
        with self._lock:
            self._buf.append(msg)

    def tail(self, lines: int) -> list[str]:
        n = max(1, int(lines))
        with self._lock:
            if not self._buf:
                return []
            if n >= len(self._buf):
                return list(self._buf)
            # deque는 슬라이싱이 안 되므로 list로 변환 후 tail
            data = list(self._buf)
            return data[-n:]


_ring_handler: _RingBufferHandler | None = None

_UVICORN_FAMILY = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
    "fastapi",
)


def _parse_log_level_from_env() -> int:
    level_name = (os.getenv("LOG_LEVEL", "INFO") or "INFO").upper().strip()
    return getattr(logging, level_name, logging.INFO)


def _apply_uvicorn_family_to_root(level: int) -> None:
    """uvicorn 기본 dictConfig(propagate=False·전용 핸들러)를 무력화하고 루트로 모은다."""
    try:
        for lname in _UVICORN_FAMILY:
            lg = logging.getLogger(lname)
            lg.handlers = []
            lg.propagate = True
            lg.setLevel(level)
    except Exception:
        pass


def harmonize_uvicorn_fastapi_loggers() -> None:
    """
    앱 기동 직후(lifespan 등)에 한 번 더 호출해도 안전.

    uvicorn이 dictConfig로 uvicorn.* 로거를 되돌린 뒤에도
    access/error 로그가 루트(터미널 미러·stderr)로 흐르도록 맞춘다.
    """
    _ensure_initialized()
    _apply_uvicorn_family_to_root(_parse_log_level_from_env())


def root_effective_level_name() -> str:
    """관리자 API 등에서 현재 루트에 적용된 레벨 표시용."""
    _ensure_initialized()
    return logging.getLevelName(logging.getLogger().getEffectiveLevel())


def _ensure_initialized() -> None:
    """핸들러/포맷터 1회 초기화 (중복 핸들러 방지)."""
    global _initialized
    global _ring_handler
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return

        from app.utils.terminal_mirror import install_stdio_mirror, is_stdio_mirror_installed

        repo_root = Path(__file__).resolve().parents[2]

        level = _parse_log_level_from_env()

        # StreamHandler 가 붙기 전에 터미널 미러를 건다(같은 sys.stderr 를 가리키게).
        install_stdio_mirror()

        fmt = "%(asctime)s [JJW] %(levelname)s %(name)s - %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

        root = logging.getLogger()
        root.setLevel(level)

        # 기존 핸들러 유지 + 우리 핸들러 중복 방지
        existing_ids = {id(h) for h in root.handlers}

        _ring_handler = None
        # 미러 끄면 예전처럼 logging 링버퍼만(미러와 이중 적재 방지)
        if not is_stdio_mirror_installed():
            ring_capacity = int(os.getenv("LOG_RING_MAX_LINES", "5000") or 5000)
            _ring_handler = _RingBufferHandler(capacity=ring_capacity)
            _ring_handler.setLevel(level)
            _ring_handler.setFormatter(formatter)
            if id(_ring_handler) not in existing_ids:
                root.addHandler(_ring_handler)

        stream = logging.StreamHandler()
        stream.setLevel(level)
        stream.setFormatter(formatter)
        if id(stream) not in existing_ids:
            root.addHandler(stream)

        # 파일 로깅은 로컬/필요 시에만 사용. (K8s에선 stdout 수집이 정석)
        # LOG_TO_FILE=1 이면 파일 로깅 활성화
        log_to_file = (os.getenv("LOG_TO_FILE", "") or "").strip().lower() in ("1", "true", "yes", "y", "on")
        if log_to_file:
            log_dir = Path(os.getenv("LOG_DIR", str(repo_root / "log"))).expanduser()
            log_dir.mkdir(parents=True, exist_ok=True)
            file_name = (os.getenv("LOG_FILE_NAME", "app.log") or "app.log").strip()
            max_bytes = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)) or (10 * 1024 * 1024))
            backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10") or 10)

            file_path = (log_dir / file_name).resolve()
            file_handler = RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            if id(file_handler) not in existing_ids:
                root.addHandler(file_handler)

        # uvicorn/fastapi 기본 로거도 root로 흘리기
        #
        # uvicorn은 자체 핸들러를 달고 propagate=False인 경우가 많아서,
        # root에 붙인 핸들러/터미널 미러(admin/logs memory)로 로그가 들어오지 않을 수 있다.
        # 여기서는 "로그를 하나로 모으는" 쪽을 우선하여, uvicorn 계열 로거의 핸들러를 제거하고
        # propagate=True로 설정한다(루트 포맷/[JJW] 통일 + 터미널과 동일한 tail).
        _apply_uvicorn_family_to_root(level)

        _initialized = True


def get_logger(name: str | None = None) -> logging.Logger:
    """
    공용 로거 반환.

    사용 예:
      - log = get_logger(__name__)
      - log = get_logger("stock_scheduler")
    """
    _ensure_initialized()
    return logging.getLogger(name or "jjw")


def tail_memory_logs(lines: int = 250) -> str:
    """
    파일 로그가 없는 환경(K8s stdout 기본)에서도 동작하는 tail.

    기본: 터미널 stdout/stderr 과 동일한 내용(terminal_mirror).
    TERMINAL_LOG_MIRROR=0 일 때만 logging 링버퍼.
    """
    _ensure_initialized()
    from app.utils.terminal_mirror import is_stdio_mirror_installed, tail_stdio_mirror

    if is_stdio_mirror_installed():
        return tail_stdio_mirror(lines)
    if _ring_handler:
        return "\n".join(_ring_handler.tail(lines))
    return ""

