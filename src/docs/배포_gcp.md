# Trader-AI 배포 가이드 (GCP Cloud Run)

이 문서는 **Kubernetes 없이** Google Cloud의 **Cloud Run**으로 앱을 띄우는 절차를 정리합니다.

- **백엔드(API)**: 레포 루트 `Dockerfile` → Cloud Run 서비스 `trader-ai-backend`
- **프론트(웹)**: `frontend/Dockerfile` → Cloud Run 서비스 `trader-ai-frontend`
- **ML 추론(선택)**: `ml/Dockerfile` → Cloud Run 서비스 `trader-ai-ml`

> 권장 운영 형태는 **Cloud Run 서비스 3개**(API, WEB, ML) 또는 **API+WEB만**(추론은 로컬 적재)입니다.  
> WEB은 브라우저가 API를 **직접 호출**하도록 `VITE_API_BASE`를 빌드 시 주입합니다.

---

## 0. 전제

- GCP 프로젝트 생성 및 결제 연결
- 로컬 `gcloud` 설치 및 로그인
- 아래 API 활성화:
  - Cloud Run (`run.googleapis.com`)
  - Artifact Registry (`artifactregistry.googleapis.com`)
  - Cloud Build (`cloudbuild.googleapis.com`) — (권장) 원격 빌드 시
  - Secret Manager (`secretmanager.googleapis.com`) — (권장) 시크릿 관리 시

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud config set run/region <REGION>
```

> **실전 배포 기록(2026-05-07)**  
> - project: `apt-bonbon-494101-b5`  
> - region: `us-central1`  
> - Cloud Run services:
>   - API: `trader-ai-backend`
>   - WEB: `trader-ai-frontend`
>   - ML: `trader-ai-ml`

---

## 1. Artifact Registry 준비 (컨테이너 레지스트리)

Docker 이미지를 올릴 저장소를 만듭니다.

```bash
gcloud artifacts repositories create trader-ai \
  --repository-format=docker \
  --location <REGION> \
  --description "trader-ai containers"
```

도커가 Artifact Registry에 푸시할 수 있도록 인증 설정:

```bash
gcloud auth configure-docker <REGION>-docker.pkg.dev
```

이후 이미지 태그는 다음 형태를 씁니다.

- `<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-backend:<TAG>`
- `<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-frontend:<TAG>`
- `<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-ml:<TAG>`

---

## 2. ML 추론 서비스 (`trader-ai-ml`)

TensorFlow·모델 파일(`predict_model/model/...`)은 이미지 용량이 크므로 **API와 분리**한 전용 서비스입니다.

### 빌드 & 푸시 (레포 루트에서)

```bash
TAG=$(date +%Y%m%d-%H%M)
IMAGE="<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-ml:${TAG}"

docker buildx build --platform linux/amd64 -f ml/Dockerfile -t "${IMAGE}" --push .
```

### Cloud Run 배포

- 포트: 컨테이너는 **8080**(Cloud Run이 `PORT` 주입 시 해당 포트로 기동)
- 메모리: 추론 부하에 따라 **4Gi·CPU 2** 권장(부족하면 OOM)
- 타임아웃: 기본 300초보다 길게 — 예: `--timeout 900`
- 환경변수 파일 예시: `deploy/cloudrun/env.ml.yaml`  
  - 필수: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`(또는 service 역할에 해당하는 키), `PREDICT_MODEL_DIR`
  - 선택: `ML_INFERENCE_AUTH_TOKEN` — 설정 시 `POST /inference/run`에 `Authorization: Bearer ...` 필요

```bash
gcloud run deploy trader-ai-ml \
  --image "${IMAGE}" \
  --region "<REGION>" \
  --port 8080 \
  --memory 4Gi --cpu 2 --timeout 900 \
  --allow-unauthenticated \
  --env-vars-file deploy/cloudrun/env.ml.yaml
```

### 헬스 체크 경로

- **`GET /health`** 권장  
  일부 환경에서 **`GET /healthz`가 Google 프런트에서 404**로 막히는 현상이 있어 ML 서비스는 **`/health`**를 사용합니다.
- API 문서: `GET /docs`, `GET /openapi.json`

### 백엔드와 연결

백엔드 Cloud Run에 다음을 설정합니다(`app/core/config.py`).

| 변수 | 설명 |
|------|------|
| `ML_SERVICE_URL` | `trader-ai-ml`의 **베이스 URL**(예: `https://trader-ai-ml-xxxxx-uc.a.run.app`). **비우면** 백엔드 프로세스 안에서 `run_inference` 직접 실행(로컬·모델 동봉 이미지용) |
| `ML_SERVICE_AUTH_TOKEN` | 선택. `env.ml.yaml`의 `ML_INFERENCE_AUTH_TOKEN`과 동일 값 |

배포 후 `deploy/cloudrun/env.yaml`에 `ML_SERVICE_URL`을 채우고 백엔드를 재배포하거나:

```bash
gcloud run services update trader-ai-backend \
  --region "<REGION>" \
  --update-env-vars "ML_SERVICE_URL=https://<YOUR_TRADER_AI_ML_HOST>"
```

### 동작 요약

- **자동**: 경제 데이터 갱신 후 신규 행이 있으면 스케줄러가 `trigger_inference()` → ML의 `POST /inference/run`
- **수동(관리자)**: 기존 `POST /admin/inference/trigger` → 동일하게 ML 호출
- **로컬 수동 적재**: 로컬에서 `uv run python predict_model/predict/run_inference.py` 실행 후 DB만 갱신해도, 프론트/백엔드는 **`stock_analysis_results` / `predicted_stocks`**를 읽으므로 동일하게 동작 (`GET /admin/inference/status` 기준도 DB 기준)

---

## 3. 백엔드(API) 빌드 & 푸시

### A) Cloud Build로 빌드 (권장)

레포 루트에서:

```bash
TAG=$(date +%Y%m%d-%H%M)
IMAGE="<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-backend:${TAG}"

gcloud builds submit --tag "${IMAGE}" .
```

> **참고(실전 배포에서 겪은 이슈)**  
> Cloud Build는 프로젝트/계정/쿼터 상태에 따라 `QUEUED`가 오래 걸릴 수 있습니다.  
> 이 경우 아래 “로컬 buildx로 amd64 빌드 후 push” 방식이 더 빠르게 해결됩니다.

### B) 로컬 Docker로 빌드 (선택)

```bash
TAG=$(date +%Y%m%d-%H%M)
IMAGE="<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-backend:${TAG}"

# (권장) Apple Silicon(macOS arm64)에서 Cloud Run(amd64)로 올릴 때는 buildx로 linux/amd64 빌드
# buildx가 없으면 설치/연결 필요: docker-buildx(Homebrew) 설치 후 ~/.docker/cli-plugins 에 symlink
docker buildx build --platform linux/amd64 -f Dockerfile -t "${IMAGE}" --push .
```

---

## 4. 백엔드(API) Cloud Run 배포

기본 배포 예시:

```bash
gcloud run deploy trader-ai-backend \
  --image "<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-backend:<TAG>" \
  --region "<REGION>" \
  --port 8000 \
  --allow-unauthenticated
```

> 운영에서 인증이 필요하면 `--no-allow-unauthenticated`로 바꾸고, 프론트(또는 사용자) 접근을 IAP/Cloud Load Balancer/Cloud Armor 등과 함께 설계하세요.

### 환경변수/시크릿

이 프로젝트는 `app/core/config.py`를 통해 환경변수로 동작이 바뀝니다.
Cloud Run에서는 아래 중 하나로 주입합니다.

- **환경변수**: `--set-env-vars KEY=VALUE,...`
- **Secret Manager**: `--set-secrets KEY=secret-name:latest`

예시(키 이름은 실제 사용하는 값에 맞게 조정):

```bash
gcloud run services update trader-ai-backend \
  --region "<REGION>" \
  --set-env-vars "TZ=Asia/Seoul"
```

### env 파일로 한 번에 주입(실전 배포 방식)

Cloud Run CLI는 `--env-vars-file`을 지원합니다.

- 예시 파일: `deploy/cloudrun/env.yaml`
- 적용:

```bash
gcloud run deploy trader-ai-backend \
  --image "<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-backend:<TAG>" \
  --region "<REGION>" \
  --port 8000 \
  --allow-unauthenticated \
  --env-vars-file deploy/cloudrun/env.yaml
```

> **보안 주의(중요)**  
> `.env`에는 KIS/Supabase Service Key/Telegram/Upstage 등 민감 정보가 포함될 수 있으므로, 운영에서는 Secret Manager로 분리해 `--set-secrets`로 주입하는 것을 권장합니다.

---

## 5. 프론트(웹) 빌드 & 푸시

프론트는 `frontend/`를 빌드 컨텍스트로 사용합니다.

### A) Cloud Build (권장)

```bash
TAG=$(date +%Y%m%d-%H%M)
IMAGE="<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-frontend:${TAG}"

gcloud builds submit --tag "${IMAGE}" frontend
```

### B) 로컬 Docker (선택)

```bash
TAG=$(date +%Y%m%d-%H%M)
IMAGE="<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-frontend:${TAG}"

# 프론트는 빌드 시점에 API base URL을 주입(Vite)
docker buildx build --platform linux/amd64 \
  -f frontend/Dockerfile \
  --build-arg VITE_API_BASE="https://<YOUR_BACKEND_RUN_URL>" \
  -t "${IMAGE}" \
  --push frontend
```

---

## 6. 프론트(웹) Cloud Run 배포

프론트는 nginx가 **80 포트**로 뜹니다.

```bash
gcloud run deploy trader-ai-frontend \
  --image "<REGION>-docker.pkg.dev/<PROJECT_ID>/trader-ai/trader-ai-frontend:<TAG>" \
  --region "<REGION>" \
  --port 80 \
  --allow-unauthenticated
```

---

## 7. 프론트 ↔ 백엔드 연결 (중요)

K8s에서는 프론트 nginx가 내부 서비스(`http://trader-ai:8000/`)로 프록시했지만,
Cloud Run에서는 **API가 외부 HTTPS URL**을 가지므로 프록시 타겟을 바꿔야 합니다.

현재 레포에는 `frontend/nginx.conf`가 있으니, 아래 중 한 방식으로 정리하는 것을 권장합니다.

- **권장(단순)**: 프론트에서 API 베이스 URL을 환경(빌드 시점)로 주입하고, 브라우저가 API를 직접 호출
  - 장점: nginx 설정을 환경별로 바꾸지 않아도 됨
  - 단점: CORS 설정 필요
- **대안**: nginx가 `/api/`를 **Cloud Run API URL**로 프록시
  - 장점: 동일 오리진 유지(브라우저 CORS 회피)
  - 단점: Cloud Run 서비스 URL이 환경마다 달라 구성 관리가 필요

### (권장) 브라우저 직접 호출로 전환 시 체크리스트

- 백엔드에 `CORS_ALLOWED_ORIGINS` 같은 환경변수/설정이 있다면, `trader-ai-web`의 도메인을 허용
- 프론트의 `frontend/src/api/index.ts`에서 API 베이스를 환경변수로 받도록 구성

### 실전 적용(이 레포에서 수행한 변경)

- `frontend/src/api/index.ts`:
  - `BASE = import.meta.env.VITE_API_BASE || '/api'` 형태로 변경
- `frontend/Dockerfile`:
  - `ARG VITE_API_BASE` / `ENV VITE_API_BASE=...` 추가
- `frontend/nginx.conf`:
  - Cloud Run에서 존재하지 않는 K8s upstream(`trader-ai`) 프록시 설정을 제거  
  - (Cloud Run에서 nginx가 `host not found in upstream "trader-ai"`로 기동 실패했기 때문)

---

## 8. 스케줄링(자동 매수/매도 등) 운영 팁

Cloud Run은 기본적으로 **요청이 없으면 0으로 스케일 다운**될 수 있습니다.
이 프로젝트는 스케줄러가 백엔드 프로세스 안에서 도는 형태라면 아래 중 하나를 선택해야 합니다.

- **방법 A(권장)**: Cloud Scheduler로 HTTP 호출 → 백엔드의 `/admin/...` 엔드포인트 트리거
  - 장점: Cloud Run이 항상 떠 있을 필요 없음
  - 단점: “내부 스케줄러” 설계를 “외부 트리거”로 바꾸는 작업이 필요할 수 있음
- **방법 B**: 최소 인스턴스 유지(`--min-instances=1`)
  - 장점: 기존 내부 스케줄러를 그대로 쓰기 쉬움
  - 단점: 비용 증가(항상 인스턴스가 떠 있음)

최소 인스턴스 예시:

```bash
gcloud run services update trader-ai-backend \
  --region "<REGION>" \
  --min-instances 1
```

### (중요) 추론 운영 모드

- **`ML_SERVICE_URL`을 설정**하고 `trader-ai-ml`을 배포한 경우: 백엔드 이미지에 모델 파일이 없어도 경제 갱신 후·관리자 수동 추론이 ML 서비스를 호출합니다.
- **API만 띄우고 추론은 로컬에서만** 할 경우: `ML_SERVICE_URL`을 비우고 `SCHEDULE_AFTER_ECONOMIC_RUN_INFERENCE=false`로 두거나, 로컬에서 `predict_model/predict/run_inference.py`로 DB만 갱신합니다.

---

## 8. 로그/모니터링

- Cloud Run 로그: Cloud Logging에서 서비스별로 확인
- 에러 추적: 필요하면 Error Reporting/Sentry 연동 고려

---

## 10. 롤백(간단)

Cloud Run은 리비전 기반이라, 문제가 생기면 이전 리비전으로 트래픽을 돌릴 수 있습니다.

```bash
gcloud run services describe trader-ai-backend --region "<REGION>"
gcloud run services update-traffic trader-ai-backend --region "<REGION>" --to-revisions <REVISION_NAME>=100
```

---

## 부록: 실전 배포 결과(URL)

> 아래 URL은 배포 시점(2026-05-07)의 값입니다. 리비전/도메인 정책에 따라 바뀔 수 있습니다.

- API: `https://trader-ai-backend-cov7xmorca-uc.a.run.app`
  - 점검: `GET /admin/health`
- WEB: `https://trader-ai-frontend-532916917323.us-central1.run.app`
- ML: `https://trader-ai-ml-cov7xmorca-uc.a.run.app`
  - 점검: `GET /health`, API 문서: `GET /docs`

