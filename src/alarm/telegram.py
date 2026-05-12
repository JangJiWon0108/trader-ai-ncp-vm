"""텔레그램 Bot API로 알림 전송. .env 의 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 사용."""

from __future__ import annotations

from typing import Any, Literal, Optional

import requests

from app.utils.logger import get_logger

logger = get_logger(__name__)

ParseMode = Optional[Literal["HTML", "MarkdownV2"]]


def send_telegram_message(
    text: str,
    *,
    parse_mode: ParseMode = None,
    disable_notification: bool = False,
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    timeout_sec: float = 10.0,
) -> bool:
    """
    텔레그램으로 텍스트 메시지를 보냅니다.

    token/chat_id 를 넘기지 않으면 app.core.config 의 settings 값을 사용합니다.
    둘 중 하나라도 비어 있으면 전송하지 않고 False 를 반환합니다.
    """
    if not (text or "").strip():
        logger.warning("텔레그램 전송: 빈 메시지는 보내지 않습니다.")
        return False

    tok = (token or "").strip()
    cid = (chat_id or "").strip()
    if not tok or not cid:
        from app.core.config import settings

        tok = (tok or (settings.TELEGRAM_BOT_TOKEN or "")).strip()
        cid = (cid or (settings.TELEGRAM_CHAT_ID or "")).strip()

    if not tok or not cid:
        logger.warning(
            "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 가 비어 있어 알림을 보내지 않습니다."
        )
        return False

    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    safe_url = "https://api.telegram.org/bot***/sendMessage"
    payload: dict = {
        "chat_id": cid,
        "text": text,
        "disable_notification": disable_notification,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        # (connect timeout, read timeout)
        r = requests.post(url, json=payload, timeout=(timeout_sec, max(20.0, timeout_sec)))
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            logger.error("Telegram API 응답 오류: %s", data)
            return False
        return True
    except requests.RequestException as e:
        # 예외 문자열에 bot token 이 포함될 수 있어 마스킹
        msg = str(e).replace(url, safe_url).replace(tok, "***")
        logger.error("Telegram 전송 실패: %s", msg)
        return False


def send_telegram_long_text(
    text: str,
    *,
    chunk_chars: int = 4000,
    **kwargs: Any,
) -> bool:
    """
    긴 본문을 텔레그램 한도(4096자) 이하로 나눠 순차 전송합니다.

    kwargs 는 send_telegram_message 에 그대로 전달됩니다(parse_mode 등).
    """
    body = text or ""
    if len(body) <= chunk_chars:
        return send_telegram_message(body, **kwargs)

    parts: list[str] = []
    i = 0
    while i < len(body):
        parts.append(body[i : i + chunk_chars])
        i += chunk_chars

    ok_all = True
    for n, chunk in enumerate(parts, 1):
        prefix = f"[{n}/{len(parts)}]\n"
        if not send_telegram_message(prefix + chunk, **kwargs):
            ok_all = False
    return ok_all


def send_telegram_message_detailed(
    text: str,
    *,
    parse_mode: ParseMode = None,
    disable_notification: bool = False,
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    timeout_sec: float = 10.0,
) -> dict:
    """
    관리자/디버깅 용도: 전송 성공 여부 + 실패 사유를 dict로 반환.
    기존 send_telegram_message/send_telegram_long_text는 그대로 유지(호환성).
    """
    if not (text or "").strip():
        return {"sent": False, "error": "빈 메시지는 보낼 수 없습니다."}

    tok = (token or "").strip()
    cid = (chat_id or "").strip()
    if not tok or not cid:
        from app.core.config import settings

        tok = (tok or (settings.TELEGRAM_BOT_TOKEN or "")).strip()
        cid = (cid or (settings.TELEGRAM_CHAT_ID or "")).strip()

    if not tok or not cid:
        return {"sent": False, "error": "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 비어 있습니다."}

    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    safe_url = "https://api.telegram.org/bot***/sendMessage"
    payload: dict = {"chat_id": cid, "text": text, "disable_notification": disable_notification}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        r = requests.post(url, json=payload, timeout=(timeout_sec, max(20.0, timeout_sec)))
        # 텔레그램은 200이어도 ok=false가 올 수 있음
        data = r.json() if r.text else {}
        if not r.ok:
            return {"sent": False, "error": f"HTTP {r.status_code}: {data or r.text}"}
        if not isinstance(data, dict) or not data.get("ok"):
            return {"sent": False, "error": f"Telegram API ok=false: {data}"}
        return {"sent": True, "error": None}
    except requests.RequestException as e:
        msg = str(e).replace(url, safe_url).replace(tok, "***")
        return {"sent": False, "error": f"요청 실패: {msg}"}
