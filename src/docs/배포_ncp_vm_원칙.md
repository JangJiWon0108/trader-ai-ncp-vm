# NCP VM 서버 접근 원칙

## 접속 정보

| 항목 | 값 |
|------|-----|
| 호스트 | `101.79.20.188` |
| 포트 | `50022` |
| 유저 | `jwjang` |
| 비밀번호 | `jwjang` |

## 접속 방법

### 직접 접속 (터미널)

```bash
ssh jwjang@101.79.20.188 -p 50022
# 비밀번호 입력: jwjang
```

### Claude Code (AI) 에서 접속

`sshpass` 미설치 환경이므로 `expect` 사용:

```bash
expect -c '
spawn ssh -o StrictHostKeyChecking=no jwjang@101.79.20.188 -p 50022 "<명령어>"
expect "password:"
send "jwjang\r"
expect eof
'
```

파일 수정 시 `sed` 또는 `cat > file` 방식으로 원격 편집:

```bash
expect -c '
spawn ssh -o StrictHostKeyChecking=no jwjang@101.79.20.188 -p 50022 "cat > /path/to/file << '\''EOF'\''
<내용>
EOF"
expect "password:"
send "jwjang\r"
expect eof
'
```

## 작업 원칙

## 프로젝트 서비스 (systemd 유저 서비스)

| 서비스명 | 설명 | 포트 |
|----------|------|------|
| `trader-ai-backend` | FastAPI 백엔드 | 51225 |
| `trader-ai-ml` | ML 서비스 | 51226 |
| `trader-ai-frontend` | Caddy 프론트엔드 | - |

### 서비스 제어 명령어

```bash
# 상태 확인
systemctl --user status trader-ai-backend
systemctl --user status trader-ai-ml
systemctl --user status trader-ai-frontend

# 재시작
systemctl --user restart trader-ai-backend
systemctl --user restart trader-ai-ml
systemctl --user restart trader-ai-frontend

# 로그 확인
journalctl --user -u trader-ai-backend -n 50 --no-pager
```

## 작업 원칙

### 반드시 지켜야 하는 규칙

| 원칙 | 설명 |
|------|------|
| **jwjang 유저만 사용** | `sudo su` 등 다른 유저 전환 금지 |
| **파일 삭제 금지** | `rm`, `rmdir` 등 삭제 명령 실행 전 반드시 사용자 확인 |
| **환경변수/설정 변경 금지** | `.env`, 설정 파일 수정 전 사용자 확인 |
| **패키지 설치 금지** | `pip install`, `apt install` 등 시스템 변경 전 사용자 확인 |

### AI(Claude)가 자율적으로 할 수 있는 작업

- 파일 내용 읽기 (`cat`, `less`)
- 소스코드 수정 (기존 파일 내용 변경)
- 로그 확인
- 프로세스/서비스 상태 확인 (`ps`, `systemctl status`)
- 디렉토리 탐색 (`ls`, `find`)
- **`trader-ai-backend`, `trader-ai-ml`, `trader-ai-frontend` 서비스 빌드/재시작** (소스 수정 후 반영 포함)

### AI(Claude)가 반드시 사용자에게 물어봐야 하는 작업

- 파일 삭제 또는 이동
- trader-ai 3개 서비스 외 다른 서비스/프로세스 재시작 또는 중단
- 새 파일/디렉토리 생성 (소스코드 외)
- 패키지 설치 또는 업그레이드
- 권한 변경 (`chmod`, `chown`)
- `crontab` 수정
- 네트워크 설정 변경

## Caddyfile 구조 (필수)

경로: `/home/jwjang/work/trader-ai/config/Caddyfile`

```
:51227 {
    handle /api/* {
        uri strip_prefix /api
        reverse_proxy localhost:51225
    }

    handle {
        root * /home/jwjang/work/trader-ai/src/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

> `/api/*` 프록시 규칙이 없으면 프론트엔드 API 호출이 모두 `index.html`(HTML)을 받아
> "Unexpected token '<'" JSON 파싱 오류 발생.

## 프론트엔드 배포 주의사항

### `scp`로 dist 업로드 시 — 중첩 경로 주의

서버 dist 경로: `/home/jwjang/work/trader-ai/src/frontend/dist`

**잘못된 방법 (dist/dist/ 중첩 생성됨):**
```bash
scp -r /local/frontend/dist/ jwjang@서버:/home/.../dist/
# → 서버에 dist/dist/ 로 복사됨
```

**올바른 방법 (파일만 복사):**
```bash
scp -r /local/frontend/dist/* jwjang@서버:/home/.../dist/
# → 서버 dist/ 안에 assets/, index.html 등 바로 복사됨
```

> `dist/`(슬래시 포함 디렉토리) 를 scp 대상 디렉토리 안으로 보내면 디렉토리 자체가 복사되어 중첩된다.
> `dist/*`(글로브) 를 쓰면 내부 파일만 복사된다.

## 팀 서버 공유 유의사항

- 이 서버는 **팀 공유 서버**로, 다른 팀원의 작업에 영향을 줄 수 있음
- 작업 전 현재 실행 중인 서비스/프로세스 확인 권장
- 대규모 변경은 팀원과 사전 협의 후 진행
- 작업 경로: `/home/jwjang/work/trader-ai`
