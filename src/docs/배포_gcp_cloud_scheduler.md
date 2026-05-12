## Trader-AI (GCP) Cloud Scheduler로 Cloud Run keep-alive 구성

이 문서는 **Cloud Run 위에서 “프로세스 내부 스케줄러(schedule/thread)”를 계속 쓰고 싶은 상황**에서,
Cloud Run이 **idle(트래픽 없음) 시 인스턴스를 내리는 동작(scale-to-zero / instance 회수)** 때문에 스케줄이 끊기거나
인스턴스가 여러 개로 늘면서 **스케줄이 중복 실행되는 문제**를 완화하기 위해,
**Cloud Scheduler가 주기적으로 API를 호출해 인스턴스를 warm 상태로 유지(keep-alive)** 하는 구성을 정리합니다.

> 권장 아키텍처(정석)는 “스케줄을 Cloud Run 밖으로 빼서 Cloud Scheduler가 작업 트리거를 호출”하는 형태입니다.
> 다만 본 레포는 현재 `app/main.py`의 lifespan에서 내부 스케줄러를 기동하는 구조라,
> **코드 변경 없이** 운영 안정성을 올리는 “차선책”으로 keep-alive를 사용합니다.

---

## 왜 필요한가?

이 프로젝트는 백엔드 프로세스 안에서 아래 작업을 스케줄로 실행합니다.

- **경제 데이터 업데이트**: `SCHEDULE_ECONOMIC_UPDATE_TIME` (예: `22:00`, KST)
- **자동 매수**: `SCHEDULE_AUTO_BUY_TIME` (예: `22:45`, KST)
- **자동 매도 점검**: `SCHEDULE_AUTO_SELL_INTERVAL_MIN` (예: 3분)

Cloud Run은 기본적으로 **요청 기반 서비스**라서, 요청이 끊기면 인스턴스가 내려갈 수 있습니다.
또한 트래픽이 순간적으로 늘면 인스턴스가 여러 개로 **스케일아웃**할 수 있는데,
이 경우 “내부 스케줄러”는 인스턴스 수만큼 각각 돌아 **중복 실행**이 발생합니다.

실제로 이 프로젝트 백엔드 로그를 분석하면:

- **idle 후 종료까지 시간**: 마지막 요청 이후 대략 **15분 전후**에 `Shutting down`이 발생하는 패턴이 관측됨
- **중복 스케줄 실행**: 같은 시각의 스케줄 로그가 서로 다른 `instanceId`에서 동시에 발생(인스턴스 다중 기동)

따라서 내부 스케줄러를 계속 쓰려면 최소한 아래 중 하나가 필요합니다.

- **(권장) 스케줄을 외부 트리거로 전환**: Cloud Scheduler → `/admin/.../trigger` 호출 (멱등/락 포함)
- **(차선) keep-alive**: Cloud Scheduler가 `/admin/health` 같은 가벼운 엔드포인트를 주기 호출해 인스턴스를 warm 유지

---

## 선행 조건

### 1) Cloud Scheduler API 활성화

```bash
gcloud services enable cloudscheduler.googleapis.com --project <PROJECT_ID>
```

### 2) (중요) 중복 실행을 막기 위한 Cloud Run 스케일 제한

내부 스케줄러를 쓰는 동안은, **인스턴스가 여러 개 뜨면 스케줄도 여러 번 돌아 중복 실행**됩니다.
따라서 최소한 아래는 강하게 권장합니다.

```bash
gcloud run services update trader-ai-backend \
  --region <REGION> \
  --max-instances 1
```

> `min-instances=1` / CPU always allocated 까지 적용하면 “내려감” 자체를 줄일 수 있지만 비용이 증가합니다.
> keep-alive는 “min=0 유지” 상태에서 인스턴스가 내려가는 것을 완화하는 용도입니다.

---

## 어떤 URL을 핑(keep-alive)할까?

처음에는 `/healthz`를 쓰려 했지만, 현재 배포된 백엔드에서는 `/healthz`가 404였습니다.

대신 문서/운영에서 이미 쓰는 **`GET /admin/health`**가 200을 반환하므로,
Cloud Scheduler의 keep-alive 타겟을 `/admin/health`로 설정합니다.

간단 확인:

```bash
curl -i "https://<BACKEND_RUN_URL>/admin/health"
```

---

## A안(추천): 21:50~06:50(KST) 동안 10분마다 keep-alive

Cloud Run의 “idle 종료”가 약 15분 전후로 관측되었기 때문에,
**안전 마진을 둔 10분 간격** keep-alive가 운영상 가장 단순하고 안정적입니다.

자정(00:00) 넘어가는 구간이 있어, 크론을 3개 잡으로 쪼갰습니다.
(잡 3개는 Cloud Scheduler 무료 티어 범위에 들어갈 가능성이 높습니다.)

### 생성/업데이트 커맨드(예시)

아래는 `us-central1` 기준 예시입니다.

- `REGION`: `us-central1`
- `TIME_ZONE`: `Asia/Seoul`
- `URI`: `https://<BACKEND_RUN_URL>/admin/health`

```bash
REGION=us-central1
PROJECT=<PROJECT_ID>
BASE_URL="https://<BACKEND_RUN_URL>"

# 21:50 (KST) 1회
gcloud scheduler jobs create http trader-ai-backend-keepalive-2150 \
  --location "$REGION" --project "$PROJECT" \
  --schedule "50 21 * * *" --time-zone "Asia/Seoul" \
  --uri "$BASE_URL/admin/health" --http-method GET \
  --attempt-deadline 30s --max-retry-attempts 3

# 22:00~23:50 (KST) 10분마다
gcloud scheduler jobs create http trader-ai-backend-keepalive-22-23 \
  --location "$REGION" --project "$PROJECT" \
  --schedule "*/10 22-23 * * *" --time-zone "Asia/Seoul" \
  --uri "$BASE_URL/admin/health" --http-method GET \
  --attempt-deadline 30s --max-retry-attempts 3

# 00:00~06:50 (KST) 10분마다 (06:10을 포함하기 위해 06:50까지는 허용)
gcloud scheduler jobs create http trader-ai-backend-keepalive-00-06 \
  --location "$REGION" --project "$PROJECT" \
  --schedule "*/10 0-6 * * *" --time-zone "Asia/Seoul" \
  --uri "$BASE_URL/admin/health" --http-method GET \
  --attempt-deadline 30s --max-retry-attempts 3
```

잡 목록 확인:

```bash
gcloud scheduler jobs list \
  --location us-central1 \
  --project <PROJECT_ID> \
  --format='table(name,state,schedule,timeZone,target.httpTarget.uri)'
```

---

## 테스트(수동 실행) 및 검증

### 1) 잡 수동 실행

```bash
gcloud scheduler jobs run trader-ai-backend-keepalive-22-23 \
  --location us-central1 --project <PROJECT_ID>
```

### 2) Cloud Run에서 실제로 호출이 들어왔는지 확인

Cloud Scheduler 호출은 보통 `httpRequest.userAgent`에 `Google-Cloud-Scheduler`가 찍힙니다.

```bash
gcloud logging read \
  'resource.type="cloud_run_revision"
   AND resource.labels.service_name="trader-ai-backend"
   AND httpRequest.userAgent:"Google-Cloud-Scheduler"' \
  --project <PROJECT_ID> \
  --limit 20 \
  --format='value(timestamp,httpRequest.requestMethod,httpRequest.requestUrl,httpRequest.status,labels.instanceId,resource.labels.revision_name)'
```

정상이라면 `GET .../admin/health 200` 로그가 보여야 합니다.

---

## 비용(대략)

- **Cloud Scheduler**: 잡 1개당 약 **$0.10/월**, 무료 티어로 **월 3개 잡 무료**(빌링 계정 단위)
- **Cloud Run 요청 비용**: keep-alive는 월 수천 회 수준이라 요청 과금은 거의 미미

---

## 운영 주의사항(중요)

- keep-alive는 **내부 스케줄러를 “안 끊기게” 도와주는 보조책**이지, “정확히 1회 실행”을 보장하지 않습니다.
- 내부 스케줄러를 유지하는 동안은 **`--max-instances 1`이 사실상 필수**입니다.
  인스턴스가 2개 이상 뜨면 스케줄이 중복 실행됩니다.
- 장기적으로는 “Cloud Scheduler → 작업 트리거”로 설계를 전환하고,
  작업 실행에 **멱등성/락(DB 기반)**을 넣는 것이 가장 안전합니다.

