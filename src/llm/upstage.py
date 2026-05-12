"""
Upstage LLM (OpenAI-compatible API) 래퍼.

환경:
- `.env` 의 UPSTAGE_API_KEY
- `.env` 의 UPSTAGE_MODEL_ID (기본값: solar-pro)
- base_url 기본값: https://api.upstage.ai/v2
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class UpstageApiError(RuntimeError):
    """Upstage(OpenAI 호환) API 호출/응답 오류."""


def generate_content(
    user_text: str,
    *,
    model_id: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_sec: float = 120.0,
    temperature: float = 0.2,
) -> str:
    """
    사용자 메시지 한 덩어리를 보내고, 모델이 생성한 본문 텍스트를 반환합니다.

    model_id / api_key / base_url 를 생략하면 `app.core.config.settings` 값을 사용합니다.
    """
    if not (user_text or "").strip():
        raise UpstageApiError("user_text 가 비어 있습니다.")

    from app.core.config import settings

    key = (api_key or getattr(settings, "UPSTAGE_API_KEY", "") or "").strip()
    if not key:
        raise UpstageApiError("UPSTAGE_API_KEY 가 비어 있습니다. .env 를 확인하세요.")

    mid = (
        (model_id or getattr(settings, "UPSTAGE_MODEL_ID", "") or "").strip()
        or "solar-pro"
    )
    burl = (base_url or getattr(settings, "UPSTAGE_BASE_URL", "") or "").strip() or "https://api.upstage.ai/v2"

    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=burl)
        resp = client.chat.completions.create(
            model=mid,
            messages=[{"role": "user", "content": user_text}],
            temperature=float(temperature),
            timeout=float(timeout_sec),
        )
    except Exception as e:
        raise UpstageApiError(f"Upstage 요청 실패: {e}") from e

    try:
        choices = getattr(resp, "choices", None) or []
        if not choices:
            raise UpstageApiError("응답에 choices 없음")
        msg = getattr(choices[0], "message", None)
        content = (getattr(msg, "content", None) or "").strip()
        if not content:
            logger.warning("Upstage 응답 content 비어 있음: %s", getattr(resp, "model_dump", lambda: resp)())
            return "(빈 텍스트 응답)"
        return content
    except UpstageApiError:
        raise
    except Exception as e:
        raise UpstageApiError(f"응답 파싱 실패: {e}") from e


def get_llm_answer(user_text: str, **kwargs: Any) -> str:
    """질의 한 번 → 답변 텍스트 (`generate_content` 별칭)."""
    return generate_content(user_text, **kwargs)

