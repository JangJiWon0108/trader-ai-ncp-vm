"""
LLM 래퍼 재노출 — Upstage(OpenAI 호환 API)만 사용.
"""

from llm.upstage import UpstageApiError, generate_content, get_llm_answer

# 예전 코드가 `from llm import GeminiApiError` 를 쓰는 경우를 위한 별칭
GeminiApiError = UpstageApiError

__all__ = ["UpstageApiError", "GeminiApiError", "generate_content", "get_llm_answer"]
