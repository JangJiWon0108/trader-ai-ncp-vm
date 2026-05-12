# ML 추론 전용 — Cloud Run Service (trader-ai-ml)
# 빌드: 레포 루트에서  docker build -f ml/Dockerfile -t ... .
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul

# 모델 실경로는 COPY 직후 RUN 에서 predict_model/model/bundled 로 고정(한글·NFD 이슈 방지).

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        tzdata \
    && ln -snf /usr/share/zoneinfo/Asia/Seoul /etc/localtime \
    && echo "Asia/Seoul" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN python -m pip install --no-cache-dir uv \
    && UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-dev --group ml \
    && rm -rf /tmp/uv-cache /root/.cache/uv

COPY . .

# 한글 디렉터리명·호스트 NFD vs 리눅스 NFC 불일치로 model_meta.json 을 못 찾는 문제 방지:
# predict_model/model 아래 v7_* 중 model_meta.json 이 있는 디렉터리를 ASCII 경로로 복사한다.
RUN set -eux; \
    found=""; \
    for d in /app/predict_model/model/v7_*/; do \
      [ -d "$d" ] || continue; \
      d="${d%/}"; \
      if [ -f "$d/model_meta.json" ]; then found="$d"; break; fi; \
    done; \
    if [ -z "$found" ]; then \
      echo "ERROR: predict_model/model 아래 v7_* 모델( model_meta.json 포함 )이 없습니다." >&2; \
      ls -la /app/predict_model/model 2>/dev/null || echo "(predict_model/model 없음)" >&2; \
      exit 1; \
    fi; \
    rm -rf /app/predict_model/model/bundled; \
    mkdir -p /app/predict_model/model/bundled; \
    cp -a "$found"/. /app/predict_model/model/bundled/

ENV PREDICT_MODEL_DIR=predict_model/model/bundled

EXPOSE 8080

# Cloud Run 은 PORT 주입 — 미설정 시 8080
CMD ["/bin/sh", "-c", "exec /app/.venv/bin/python -m uvicorn ml_service.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
