"""
ML 추론 실행 — 원격 Cloud Run(trader-ai-ml) 또는 로컬 run_inference.

환경변수(및 Settings):
- ML_SERVICE_URL: 설정 시 POST {URL}/inference/run 호출
- ML_SERVICE_AUTH_TOKEN: 선택, Authorization: Bearer 로 전송

ML_SERVICE_URL 이 비어 있으면 기존처럼 같은 프로세스에서 `run_inference_and_save_to_db` 실행
(로컬 개발·모델 파일이 백엔드 컨테이너에 있을 때).
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from app.core.config import settings


def trigger_inference(*, write_db: bool = True) -> dict[str, Any]:
    base = (settings.ML_SERVICE_URL or "").strip().rstrip("/")
    if not base:
        from predict_model.predict.run_inference import run_inference_and_save_to_db

        return run_inference_and_save_to_db(model_dir=settings.predict_model_path, write_db=write_db)

    token = (settings.ML_SERVICE_AUTH_TOKEN or "").strip()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # 추론은 TensorFlow·대용량 I/O로 수 분 걸릴 수 있음
    timeout_sec = float(os.environ.get("ML_SERVICE_TIMEOUT_SEC", "900"))

    url = f"{base}/inference/run"
    resp = requests.post(
        url,
        json={"write_db": write_db},
        headers=headers,
        timeout=timeout_sec,
    )

    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}

    if resp.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else str(payload)
        raise RuntimeError(f"ML service HTTP {resp.status_code}: {detail}")

    if not (isinstance(payload, dict) and payload.get("success")):
        raise RuntimeError(f"ML service returned failure: {json.dumps(payload, ensure_ascii=False)[:2000]}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("ML service response missing result dict")
    return result
