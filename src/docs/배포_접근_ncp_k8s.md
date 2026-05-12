# 배포 접근 · 장애 분석 가이드 (AI Agent용)

이 문서는 **이미 빌드·푸시된 Docker 이미지**와 **클러스터에 올라간 Kubernetes 리소스**에만 접근해, 문제 발생 시 **로그·이벤트·상태**를 파악하고 원인을 좁히기 위한 절차를 정의한다.  
Cursor·Claude 등 **자동화 에이전트**가 터미널에서 조작할 때의 **허용 범위와 금지 사항**을 반드시 따른다.

**맥락:** Docker 빌드·푸시는 사용자 **로컬 macOS + Colima** 에서 수행하고, 레지스트리는 **Docker Hub (`jangjiwon/...`)** 이다. 반면 **Kubernetes는 공용 계정·공용 클러스터**이므로, 다른 팀·다른 앱에 영향을 주지 않도록 **`trader-ai-jjw` 네임스페이스만** 다루는 규칙을 강하게 둔다.

---

## 절대 준수: 네임스페이스 스코프 (Never 위반)

- **허용:** Kubernetes API 조작은 **`trader-ai-jjw` 네임스페이스 안의 리소스만** 대상으로 한다. (공용 클러스터이므로 이 범위를 벗어나면 안 된다.)
- **금지 (Never — 예외 없음):**  
  - 다른 네임스페이스의 리소스 조회·수정·삭제·생성  
  - 네임스페이스 미지정으로 전체 클러스터를 훑는 패턴(실수로 다른 워크로드에 닿을 수 있는 명령)  
  - 클러스터 스코프 리소스의 임의 변경(노드, ClusterRole, StorageClass, CRD 등) — **본 프로젝트 장애 분석과 무관하면 수행하지 않는다.**

**모든 `kubectl` 명령에는 `-n trader-ai-jjw`를 붙인다.**  
`--all-namespaces` / `-A` 를 이 목적으로 사용하지 않는다.

---

## 이 네임스페이스에서 다루는 주요 리소스 이름

| 종류 | 이름 |
|------|------|
| Deployment (API) | `trader-ai` |
| Deployment (웹) | `trader-ai-web` |
| Service (API) | `trader-ai` |
| Service (웹) | `trader-ai-web` |
| ConfigMap | `trader-ai-config` |
| Secret | `trader-ai-secrets` |
| PodDisruptionBudget | `trader-ai-pdb`, `trader-ai-web-pdb` |

---

## 권장: 읽기 전용 진단 순서

1. **Pod 상태**

```bash
kubectl -n trader-ai-jjw get pods -o wide
kubectl -n trader-ai-jjw describe pod -l app=trader-ai
kubectl -n trader-ai-jjw describe pod -l app=trader-ai-web
```

2. **이벤트 (스케줄 실패·OOM·프로브 실패 등)**

```bash
kubectl -n trader-ai-jjw get events --sort-by='.lastTimestamp' | tail -n 50
```

3. **로그 (현재 컨테이너)**

```bash
kubectl -n trader-ai-jjw logs deploy/trader-ai --tail=200
kubectl -n trader-ai-jjw logs deploy/trader-ai-web --tail=200
```

4. **이전 컨테이너(재시작 직후 원인 추적)**

```bash
kubectl -n trader-ai-jjw logs deploy/trader-ai --previous --tail=200
```

5. **Deployment / Service 요약**

```bash
kubectl -n trader-ai-jjw get deploy,svc,pdb
kubectl -n trader-ai-jjw describe deploy/trader-ai
kubectl -n trader-ai-jjw describe deploy/trader-ai-web
```

6. **로컬에서 API만 잠깐 확인할 때 (선택)** — 다른 네임스페이스·다른 서비스로 포워딩하지 않는다.

```bash
kubectl -n trader-ai-jjw port-forward svc/trader-ai 8000:80
# 다른 터미널: curl -sS http://127.0.0.1:8000/healthz
```

웹 경유(`/api` 프록시) 확인:

```bash
kubectl -n trader-ai-jjw port-forward svc/trader-ai-web 8080:80
# curl -sS http://127.0.0.1:8080/healthz
# curl -sS http://127.0.0.1:8080/api/healthz
```

---

## Docker 이미지 (레지스트리·로컬)

**런타임:** 사용자 **로컬 macOS** 에서 **Docker Desktop 대신 [Colima](https://github.com/abiosoft/colima)** 를 쓴다. Colima가 Linux VM 위에서 Docker 호환 데몬을 띄우고, 호스트의 **`docker` CLI가 Colima의 소켓(예: `~/.colima/default/docker.sock`)을 바라보도록** 연결된다. 아래 `docker …` 명령은 **Colima 백엔드**를 통해 실행된다고 가정한다. Colima가 꺼져 있으면 `colima status` 등으로 기동 여부를 먼저 확인한다.

**레지스트리:** 푸시 대상은 **Docker Hub**, 이미지 접두는 **`jangjiwon/`** (예: `jangjiwon/trader-ai:latest`, `jangjiwon/trader-ai-web:latest`). 로컬·개인 계정 범위라 K8s만큼의 공용 제약은 없다.

- **읽기:** `docker images` 로 태그·크기·생성 시각 확인, `docker inspect jangjiwon/trader-ai:latest` 등으로 엔트리포인트·환경변수 힌트 수집.
- **로컬 재현(선택):** 동일 태그를 `docker run` 할 때 **시크릿·실계좌 키를 인자로 넘기지 않는다.** 필요하면 사용자가 제공한 샌드박스 env 파일만 사용하도록 안내한다.
- **금지:** 다른 팀 이미지의 force push/delete, 무관한 컨테이너 정지.

---

## Secret·민감 정보

- `kubectl get secret -n trader-ai-jjw trader-ai-secrets -o yaml` 은 **디버깅 시 최소한만** 사용한다.
- 로그·이벤트에 토큰·키가 노출될 수 있으므로, 에이전트 출력·저장 시 **마스킹**하거나 사용자에게만 요약한다.
- Secret 값을 **임의로 수정·재생성**하지 않는다. 변경이 필요하면 사용자 승인 후 절차를 문서화한다.

---

## 쓰기 작업 (재시작·스케일·삭제)

- 기본 원칙: **읽기로 끝낼 수 있으면 쓰기를 하지 않는다.**
- 사용자가 명시적으로 “재시작해줘” 등을 요청한 경우에만 예를 들어:

```bash
kubectl -n trader-ai-jjw rollout restart deploy/trader-ai
kubectl -n trader-ai-jjw rollout restart deploy/trader-ai-web
```

- `kubectl delete` 는 **대상 리소스 이름을 풀네임으로 한정**하고, `-n trader-ai-jjw` 외 네임스페이스에는 절대 사용하지 않는다.  
- `kubectl apply -f` 는 **이 레포의 `k8s/`·`frontend/k8s/` 매니페스트만** 사용하며, 경로를 잘못 집어 다른 디렉터리 YAML을 적용하지 않도록 한다.

---

## 금지 명령 패턴 예시 (Never)

- `kubectl get pods -A` (전 네임스페이스; 본 가이드 목적에 부적합)
- `kubectl delete namespace ...`  
- `kubectl drain` / 노드 조작  
- 네임스페이스 없이: `kubectl get pods`, `kubectl delete pod <name>` (다른 ns의 동명 Pod와 혼동 가능 — **항상 `-n trader-ai-jjw`**)

---

## 한 줄 요약

**`trader-ai-jjw` 안에서만 읽고 로그를 본다. 그 밖의 K8s 리소스는 never 건드린다.**
