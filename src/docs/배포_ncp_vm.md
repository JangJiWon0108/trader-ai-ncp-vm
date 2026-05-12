# NCP VM 배포 가이드 (uv 직접 실행)

Google Cloud Run 배포는 그대로 유지하면서, NCP VM에 uv로 직접 실행하는 가이드입니다.

---

## 서버 접속 정보

| 항목 | 값 |
|------|-----|
| 공인 IP | `101.79.20.188` |
| SSH 포트 | `50022` |
| OS | Ubuntu 24.04.1 LTS |
| CPU | 4코어 (AMD EPYC 9454P) |
| RAM | 15Gi |
| 디스크 | 20G (사용 3.7G / 여유 16G) |
| 계정 | `jwjang` |
| 비밀번호 | `jwjang` |

```bash
ssh jwjang@101.79.20.188 -p 50022
```

---

- 로컬 작업 경로: `/Users/n-jwjang/jjw/work/trader-ai/`
- 서버 배포 경로: `/home/jwjang/work/trader-ai/`

---

## 폴더 구조

```
trader-ai/
├── config/
│   ├── .env                  # backend/ml 환경변수
│   ├── .env.production       # frontend 빌드 환경변수
│   └── Caddyfile             # Caddy 설정
├── src/                      # 소스코드 (rsync 대상)
└── scripts/
    ├── backend/
    │   └── trader-ai-backend.service  # Backend systemd 서비스 정의 (포트 51225)
    ├── ml/
    │   └── trader-ai-ml.service       # ML systemd 서비스 정의 (포트 51226)
    └── frontend/
        ├── trader-ai-frontend.service    # Caddy systemd 서비스 정의 (포트 51227)
        └── build.sh                   # Frontend 빌드 스크립트
```

---

## 포트 구성

| 서비스 | 포트 |
|--------|------|
| Backend API | **51225** |
| ML Service | **51226** |
| Frontend (Caddy) | **51227** |

---

## 1. VM 접속 전 확인 사항

- OS: **Ubuntu 24.04.1 LTS**
- 인바운드 포트 오픈: `51225`, `51226`, `51227`, `50022`
- VM 공인 IP 주소: `101.79.20.188`

```bash
ssh jwjang@101.79.20.188 -p 50022
```

---

## 2. VM 환경 설치

> 서버 기본 Node.js는 v18이나 Vite 8이 v20+ 필요 → nvm으로 업그레이드

```bash
# [유저 로컬] nvm 설치 및 Node.js 22 업그레이드
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.bashrc
nvm install 22
nvm alias default 22

# [유저 로컬] uv 설치 (Python 3.13 자동 다운로드 포함)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env   # 또는 재접속

# [유저 로컬] Caddy 바이너리 설치 (sudo 불필요)
curl -L "https://caddyserver.com/api/download?os=linux&arch=amd64" -o ~/.local/bin/caddy
chmod +x ~/.local/bin/caddy

# 부팅 시 유저 서비스 자동 시작 활성화
loginctl enable-linger
```

---

## 3. 소스 배포 (로컬에서 실행)

VM에 필요한 파일만 전송합니다. 아래 항목은 제외합니다.

| 제외 항목 | 이유 |
|-----------|------|
| `.gcloud/`, `deploy/`, `k8s/` | GCP/Cloud Run 전용 |
| `Dockerfile`, `Dockerfile.ml`, `ml/` | Docker 전용 |
| `.dockerignore` | Docker 전용 |
| `frontend/node_modules/` | 서버에서 npm ci로 재설치 |
| `predict_model/train/` | 학습 노트북 — 추론에 불필요 |
| `documents/` | KIS API HTML 레퍼런스 문서 |
| `nasdaq100.csv` | 학습용 데이터 |
| `test_apis.py` | 로컬 테스트 전용 |
| `.env` | config/ 로 별도 복사 (scp) |
| `.git/`, `.venv/`, `__pycache__/` | git 이력 / 가상환경 / 캐시 |
| `.claude/`, `.code-review-graph/` | 개발 도구 전용 |
| `log/`, `stock_scheduler.log`, `.cache/` | 로컬 로그/캐시 |

```bash
rsync -avz --progress \
  --exclude='.gcloud/' \
  --exclude='deploy/' \
  --exclude='k8s/' \
  --exclude='Dockerfile' \
  --exclude='Dockerfile.ml' \
  --exclude='ml/' \
  --exclude='.dockerignore' \
  --exclude='frontend/node_modules/' \
  --exclude='predict_model/train/' \
  --exclude='documents/' \
  --exclude='nasdaq100.csv' \
  --exclude='test_apis.py' \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='.claude/' \
  --exclude='.code-review-graph/' \
  --exclude='log/' \
  --exclude='stock_scheduler.log' \
  --exclude='.cache/' \
  --exclude='.env' \
  --exclude='.DS_Store' \
  -e "ssh -p 50022" \
  /Users/n-jwjang/jjw/work/trader-ai/ \
  jwjang@101.79.20.188:/home/jwjang/work/trader-ai/src/
```

---

## 4. 의존성 설치 (VM에서)

```bash
# Backend + ML 의존성
cd ~/work/trader-ai/src && uv sync --frozen --no-dev --group ml

# Frontend 의존성
cd ~/work/trader-ai/src/frontend && npm ci
```

---

## 5. 환경 파일 생성 (로컬에서 실행, 최초 1회)

```bash
# 서버에 config 디렉토리 생성
ssh jwjang@101.79.20.188 -p 50022 "mkdir -p ~/work/trader-ai/config"

# 로컬 .env → 서버 config/.env 복사 (인라인 주석 제거 후 전송)
grep -v '^#' /Users/n-jwjang/jjw/work/trader-ai/.env | \
  sed 's/[[:space:]]*#.*$//' | \
  ssh jwjang@101.79.20.188 -p 50022 "cat > ~/work/trader-ai/config/.env"

# frontend 빌드 환경변수
ssh jwjang@101.79.20.188 -p 50022 "cat > ~/work/trader-ai/config/.env.production << 'EOF'
VITE_API_BASE=http://101.79.20.188:51225
EOF"

# Caddy 설정
ssh jwjang@101.79.20.188 -p 50022 "cat > ~/work/trader-ai/config/Caddyfile << 'EOF'
:51227 {
    root * /home/jwjang/work/trader-ai/src/frontend/dist
    try_files {path} /index.html
    file_server
}
EOF"
```

> `.env` 변경 시마다 위 `scp` 명령어로 재동기화.

---

## 6. 스크립트 생성 (VM에서, 최초 1회)

```bash
mkdir -p ~/work/trader-ai/scripts/{backend,ml,frontend}

# frontend build 스크립트
cat > ~/work/trader-ai/scripts/frontend/build.sh << 'EOF'
#!/bin/bash
cd /home/jwjang/work/trader-ai/src/frontend
npm ci
VITE_ENV_DIR=/home/jwjang/work/trader-ai/config npm run build
EOF
chmod +x ~/work/trader-ai/scripts/frontend/build.sh

# backend service 파일
cat > ~/work/trader-ai/scripts/backend/trader-ai-backend.service << 'EOF'
[Unit]
# 서비스 설명
Description=Trader AI Backend
# 네트워크가 준비된 후 시작
After=network.target

[Service]
# 실행 위치 (uvicorn이 app.main:app 을 찾는 기준 경로)
WorkingDirectory=/home/jwjang/work/trader-ai/src
# 환경변수 파일 경로
EnvironmentFile=/home/jwjang/work/trader-ai/config/.env
# 실행 명령어
ExecStart=/home/jwjang/work/trader-ai/src/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 51225
# 프로세스 죽으면 자동 재시작
Restart=always
# 재시작 대기 시간 (초)
RestartSec=5

[Install]
# 로그인 없이도 부팅 시 자동 시작 (loginctl enable-linger 와 함께 동작)
WantedBy=default.target
EOF

# ml service 파일
cat > ~/work/trader-ai/scripts/ml/trader-ai-ml.service << 'EOF'
[Unit]
Description=Trader AI ML Service
After=network.target

[Service]
WorkingDirectory=/home/jwjang/work/trader-ai/src
EnvironmentFile=/home/jwjang/work/trader-ai/config/.env
ExecStart=/home/jwjang/work/trader-ai/src/.venv/bin/uvicorn ml_service.main:app --host 0.0.0.0 --port 51226
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF

# caddy service 파일
cat > ~/work/trader-ai/scripts/frontend/trader-ai-frontend.service << 'EOF'
[Unit]
Description=Trader AI Frontend (Caddy)
After=network.target

[Service]
# Caddy 바이너리로 Caddyfile 설정 읽어서 정적 파일 서빙
ExecStart=/home/jwjang/.local/bin/caddy run --config /home/jwjang/work/trader-ai/config/Caddyfile
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
```

---

## 7. Frontend 빌드 (VM에서)

```bash
bash ~/work/trader-ai/scripts/frontend/build.sh
```

---

## 8. systemd 서비스 등록 (모두 user service, sudo 불필요)

```bash
mkdir -p ~/.config/systemd/user

# scripts/ 의 service 파일을 symlink
ln -s ~/work/trader-ai/scripts/backend/trader-ai-backend.service ~/.config/systemd/user/
ln -s ~/work/trader-ai/scripts/ml/trader-ai-ml.service ~/.config/systemd/user/
ln -s ~/work/trader-ai/scripts/frontend/trader-ai-frontend.service ~/.config/systemd/user/

# 활성화 및 시작
systemctl --user daemon-reload

# Backend
systemctl --user enable trader-ai-backend
systemctl --user start trader-ai-backend

# ML
systemctl --user enable trader-ai-ml
systemctl --user start trader-ai-ml

# Frontend
systemctl --user enable trader-ai-frontend
systemctl --user start trader-ai-frontend
```

---

## 9. 접속 확인

| 서비스 | URL |
|--------|-----|
| Frontend | `http://101.79.20.188:51227` |
| Backend API Docs | `http://101.79.20.188:51225/docs` |
| ML Service Health | `http://101.79.20.188:51226/health` |

---

## 10. 운영 명령어

### 시작 / 중지 / 재시작

```bash
systemctl --user start   trader-ai-backend
systemctl --user stop    trader-ai-backend
systemctl --user restart trader-ai-backend

systemctl --user start   trader-ai-ml
systemctl --user stop    trader-ai-ml
systemctl --user restart trader-ai-ml

systemctl --user start   trader-ai-frontend
systemctl --user stop    trader-ai-frontend
systemctl --user restart trader-ai-frontend
```

### 상태 확인

```bash
systemctl --user status trader-ai-backend
systemctl --user status trader-ai-ml
systemctl --user status trader-ai-frontend
```

### 로그 (실시간)

```bash
# Backend
journalctl --user -u trader-ai-backend -f

# ML
journalctl --user -u trader-ai-ml -f

# Frontend (Caddy)
journalctl --user -u trader-ai-frontend -f
```

### 코드 업데이트 후 재배포

#### A. 로컬에서 수정 후 동기화

**1. 로컬에서 rsync:**
```bash
rsync -avz --progress \
  --exclude='.gcloud/' \
  --exclude='deploy/' \
  --exclude='k8s/' \
  --exclude='Dockerfile' \
  --exclude='Dockerfile.ml' \
  --exclude='ml/' \
  --exclude='.dockerignore' \
  --exclude='frontend/node_modules/' \
  --exclude='predict_model/train/' \
  --exclude='documents/' \
  --exclude='nasdaq100.csv' \
  --exclude='test_apis.py' \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='__pycache__/' \
  --exclude='.claude/' \
  --exclude='.code-review-graph/' \
  --exclude='log/' \
  --exclude='stock_scheduler.log' \
  --exclude='.cache/' \
  --exclude='.env' \
  --exclude='.DS_Store' \
  -e "ssh -p 50022" \
  /Users/n-jwjang/jjw/work/trader-ai/ \
  jwjang@101.79.20.188:/home/jwjang/work/trader-ai/src/
```

**2. VM에서 재빌드 + 재시작:**
```bash
cd ~/work/trader-ai/src && uv sync --frozen --no-dev --group ml
bash ~/work/trader-ai/scripts/frontend/build.sh
systemctl --user restart trader-ai-backend trader-ai-ml trader-ai-frontend
```

#### B. 서버에서 직접 수정 후 재시작

```bash
# 소스 직접 편집
vi ~/work/trader-ai/src/app/...

# Python 변경 시 — 재시작만
systemctl --user restart trader-ai-backend trader-ai-ml

# Frontend 변경 시 — 재빌드 후 재시작
bash ~/work/trader-ai/scripts/frontend/build.sh
systemctl --user restart trader-ai-frontend

# 의존성 변경 시 (pyproject.toml)
cd ~/work/trader-ai/src && uv sync --frozen --no-dev --group ml
systemctl --user restart trader-ai-backend trader-ai-ml
```
