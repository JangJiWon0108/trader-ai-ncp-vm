"""
ML 추론 전용 FastAPI 앱 — Cloud Run Service(trader-ai-ml).

`predict_model.predict.run_inference.run_inference_and_save_to_db`를 호출해
Supabase의 predicted_stocks / stock_analysis_results 를 갱신한다.

인증(선택): 환경변수 ML_INFERENCE_AUTH_TOKEN 이 설정된 경우,
요청 헤더 Authorization: Bearer <token> 또는 X-ML-Auth-Token: <token> 필수.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# 레포 루트 기준으로 .env 로드(컨테이너에서는 보통 env 만 사용)
_REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_REPO_ROOT / ".env", override=False)

app = FastAPI(
    title="Trader-AI ML Inference",
    version="1.0.0",
    description="Transformer 추론 → Supabase 적재",
)


@app.get("/")
def root():
    return {"service": "trader-ai-ml", "health": "/health", "inference": "POST /inference/run", "docs": "/docs"}


def _check_auth(authorization: str | None, x_ml_auth: str | None) -> None:
    token = (os.environ.get("ML_INFERENCE_AUTH_TOKEN") or "").strip()
    if not token:
        return
    got = None
    if x_ml_auth and x_ml_auth.strip():
        got = x_ml_auth.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        got = authorization[7:].strip()
    if not got or got != token:
        raise HTTPException(status_code=401, detail="unauthorized")


class InferenceRunRequest(BaseModel):
    write_db: bool = Field(True, description="DB에 predicted_stocks / stock_analysis_results 반영")
    # 상대·절대 경로. 미지정 시 환경변수 PREDICT_MODEL_DIR
    model_dir: str | None = Field(None, description="모델 디렉터리(미지정 시 PREDICT_MODEL_DIR)")


@app.get("/health")
def health():
    """
    Cloud Run 앞단에서 `/healthz` 경로가 404로 막히는 환경이 있어 `/health` 사용.
    """
    return {"status": "ok", "service": "trader-ai-ml"}


@app.post("/inference/run")
def inference_run(
    body: InferenceRunRequest | None = None,
    authorization: str | None = Header(None),
    x_ml_auth_token: str | None = Header(None, alias="X-ML-Auth-Token"),
):
    _check_auth(authorization, x_ml_auth_token)
    body = body or InferenceRunRequest()

    raw = (body.model_dir or os.environ.get("PREDICT_MODEL_DIR") or "").strip()
    if not raw:
        raise HTTPException(
            status_code=500,
            detail="PREDICT_MODEL_DIR 환경변수 또는 model_dir 본문이 필요합니다.",
        )
    model_path = Path(raw)
    if not model_path.is_absolute():
        model_path = (_REPO_ROOT / model_path).resolve()

    from predict_model.predict.run_inference import run_inference_and_save_to_db

    try:
        result = run_inference_and_save_to_db(model_dir=model_path, write_db=body.write_db)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"inference failed: {e!s}") from e
