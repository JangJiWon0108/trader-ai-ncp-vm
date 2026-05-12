FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8000 \
    BACKEND_RELOAD=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        tzdata \
    && ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime \
    && echo "${TZ}" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

# API + ML(추론) 의존성 포함: dev 제외
RUN python -m pip install --no-cache-dir uv \
    && UV_CACHE_DIR=/tmp/uv-cache uv sync --frozen --no-dev --group ml \
    && rm -rf /tmp/uv-cache /root/.cache/uv

COPY . .

EXPOSE 8000

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
