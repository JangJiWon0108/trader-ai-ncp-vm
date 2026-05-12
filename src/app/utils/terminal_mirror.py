"""
터미널(stdout/stderr)과 동일한 출력을 메모리에 복제한다.

관리자 /admin/logs 의 memory 소스는 logging 전용 링버퍼가 아니라
여기서 모은 “실제 터미널에 찍힌 문자열”을 tail 한다.
"""

from __future__ import annotations

import os
import sys
from collections import deque
from threading import RLock

_buf_lock = RLock()
_lines: deque[str] = deque(maxlen=1)
_install_lock = RLock()
_installed = False


def _capacity() -> int:
    return max(1, int(os.getenv("LOG_RING_MAX_LINES", "5000") or 5000))


def _reset_deque_if_needed() -> None:
    global _lines
    cap = _capacity()
    if _lines.maxlen != cap:
        old = list(_lines)
        _lines = deque(old[-cap:], maxlen=cap)


def _push_line(text: str) -> None:
    if not text:
        return
    with _buf_lock:
        _reset_deque_if_needed()
        _lines.append(text)


class _StdMirrorStream:
    """원래 스트림으로 그대로 쓰고, 동일한 내용을 줄 단위로 _lines 에도 적재한다."""

    _trader_ai_stdio_mirror = True

    def __init__(self, inner):
        self._inner = inner
        self._partial = ""
        self._write_lock = RLock()

    def write(self, s: str | bytes) -> int:
        if s is None:
            return 0
        if isinstance(s, bytes):
            enc = getattr(self._inner, "encoding", None) or "utf-8"
            try:
                ss = s.decode(enc, errors="replace")
            except Exception:
                return len(s)
        else:
            ss = str(s)
        n = len(ss)
        with self._write_lock:
            try:
                self._inner.write(ss)
            except Exception:
                pass
            self._partial += ss
            while "\n" in self._partial:
                line, self._partial = self._partial.split("\n", 1)
                line = line.rstrip("\r")
                _push_line(line)
        return n

    def flush(self) -> None:
        with self._write_lock:
            try:
                self._inner.flush()
            except Exception:
                pass
            if self._partial:
                _push_line(self._partial.rstrip("\r\n"))
                self._partial = ""

    def isatty(self) -> bool:  # noqa: D401
        try:
            return self._inner.isatty()
        except Exception:
            return False

    @property
    def encoding(self) -> str | None:
        return getattr(self._inner, "encoding", None)

    def fileno(self) -> int:
        return self._inner.fileno()

    def writable(self) -> bool:
        try:
            return self._inner.writable()
        except Exception:
            return True

    def writelines(self, lines):  # type: ignore[no-untyped-def]
        for line in lines:
            self.write(line)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def install_stdio_mirror() -> None:
    """
    sys.stdout / sys.stderr 를 한 번만 감싼다.

    TERMINAL_LOG_MIRROR=0|false|off 이면 비활성 — logger 가 logging 링버퍼로만 tail 한다.
    """
    global _installed
    if _installed:
        return
    with _install_lock:
        if _installed:
            return
        raw = (os.getenv("TERMINAL_LOG_MIRROR", "1") or "").strip().lower()
        if raw in ("0", "false", "no", "off", "n"):
            _installed = True
            return
        try:
            _reset_deque_if_needed()
            if not getattr(sys.stdout, "_trader_ai_stdio_mirror", False):
                sys.stdout = _StdMirrorStream(sys.__stdout__)
            if not getattr(sys.stderr, "_trader_ai_stdio_mirror", False):
                sys.stderr = _StdMirrorStream(sys.__stderr__)
        except Exception:
            return
        _installed = True


def is_stdio_mirror_installed() -> bool:
    """True면 tail_memory_logs 가 터미널 미러 버퍼를 사용한다."""
    return bool(getattr(sys.stderr, "_trader_ai_stdio_mirror", False))


def tail_stdio_mirror(lines: int = 250) -> str:
    """최근 완결된 줄(및 flush 로 넘긴 잔여) tail."""
    n = max(1, int(lines))
    with _buf_lock:
        if not _lines:
            return ""
        if n >= len(_lines):
            return "\n".join(_lines)
        data = list(_lines)
        return "\n".join(data[-n:])
