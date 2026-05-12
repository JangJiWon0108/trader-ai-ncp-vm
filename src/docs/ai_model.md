# AI 예측 모델 상세 문서 (Transformer)

이 문서는 `predict_model/` 아래의 **주가 예측(멀티타겟 회귀) 모델**에 대해, 학습/평가/저장/추론까지 재현 가능한 수준으로 정리한 문서다.

- **학습 노트북**: `predict_model/train/train.ipynb`
- **추론 스크립트**: `predict_model/predict/run_inference.py`
- **모델 산출물 디렉토리**: `predict_model/model/<version>/`

---

## 목표(Problem Definition)

- **입력(Input)**: 최근 \(LOOKBACK\) 거래일의
  - (A) **타겟 50개 종목의 종가 시퀀스**
  - (B) **거시/시장/환율/원자재 등 경제지표 시퀀스**
- **출력(Output)**: 50개 종목 각각의 **\(FORECAST_HORIZON\) 거래일 후 종가** (벡터 50개)
- **모델 타입**: 시계열→시계열(시퀀스 입력) 기반의 **멀티아웃풋 회귀**

> `FORECAST_HORIZON=5`면 “5거래일 뒤 종가”를 예측한다.

---

## 데이터 소스 & 스키마

### 학습 데이터 테이블

- **Supabase DB**: `economic_and_stock_data`
  - 일별 1행(거래일 기준)
  - 컬럼 구성(프로젝트 기준)
    - `date` 1개
    - 경제/시장 지표 다수(노트북 기준 `ECONOMIC_FEATURES`)
    - 타겟 종목 50개(노트북 기준 `TARGET_COLUMNS`)

> 정확한 컬럼 목록은 노트북의 `TARGET_COLUMNS`, `ECONOMIC_FEATURES` 정의를 기준으로 한다.

### 예측 결과 저장(추론 이후)

프로젝트의 전체 흐름 관점에서 예측 결과는 DB 테이블에 적재되어 앱에서 사용된다.

- `predicted_stocks`: 날짜별 “예측가/실제가” 컬럼 쌍 저장
- `stock_analysis_results`: 정확도/상승확률/추천 등급 등 최종 결과 저장

---

## 전처리(Preprocessing)

`train.ipynb`의 전처리/피처 처리 핵심은 아래와 같다.

### 1) 날짜 정렬 및 결측치 처리

- **정렬**: 날짜 오름차순 정렬
- **결측치**: 주말/공휴일 등 누락 구간은 `ffill`/`bfill`로 채움
  - 목적: 시퀀스 윈도우 생성 시 NaN으로 학습이 깨지는 것을 방지

### 2) 입력 피처 분리

- **주가 입력(Stock branch)**: `TARGET_COLUMNS` (50개)
- **경제지표 입력(Econ branch)**: `ECONOMIC_FEATURES` (노트북에 정의된 리스트)

### 3) 스케일링(정규화)

신경망 입력을 위해 **0~1 범위 정규화(MinMaxScaler)** 를 적용한다.

- **스케일러 분리**: 주가와 경제지표를 동일 스케일러로 섞지 않고, 보통 “그룹 별 스케일”로 다루는 것을 전제로 한다.
- **역변환**: 추론 결과는 저장된 스케일러로 inverse transform 하여 실제 가격 단위로 복원한다.

> 저장되는 스케일러 파일은 모델 디렉토리의 `*_scaler.pkl` 형태를 따른다(예: `stock_scaler.pkl`, `econ_scaler.pkl`).

---

## 학습용 데이터셋 생성(Windowing)

### 핵심 하이퍼파라미터

- `LOOKBACK`: 과거 몇 거래일을 보고 예측할지
- `FORECAST_HORIZON`: 몇 거래일 뒤를 예측할지

### 슬라이딩 윈도우 정의

각 시점 \(i\)에 대해:

- **입력 \(X\)**:
  - 주가: \([i-LOOKBACK, \dots, i-1]\) 구간의 50개 종목 시퀀스
  - 경제: \([i-LOOKBACK, \dots, i-1]\) 구간의 경제지표 시퀀스
- **정답 \(y\)**:
  - \((i + FORECAST_HORIZON - 1)\) 시점의 50개 종목 값

즉, “과거 LOOKBACK일”로 “FORECAST_HORIZON일 뒤”의 종가를 맞히도록 학습 샘플을 만든다.

### Train/Validation 분리

노트북 기준으로 **최근 30거래일을 validation**으로 분리한다.

- 목적: 최신 구간 일반화 성능 확인(과적합 감시)
- 주의: 시계열이므로 셔플 기반 분리보다 “최근 구간 holdout”이 안전하다.

---

## 모델 구조(Model Architecture)

모델은 크게 2-브랜치(주가/경제) 구조이며, 각 브랜치에서 Transformer로 시퀀스를 인코딩한 후 합쳐서 예측한다.

### 개략 구조

- 입력1(주가 시퀀스) → Transformer 인코더 스택 → Dense → 특징벡터
- 입력2(경제 시퀀스) → Transformer 인코더 스택 → Dense → 특징벡터
- 두 특징벡터를 결합(Add 또는 Concat 계열) → Dense/Dropout/Pooling → 출력 Dense(50)

### 주요 구성요소(노트북 기준)

- Multi-Head Attention
- Feed-Forward Network(FFN)
- Dropout
- GlobalAveragePooling 계열

> 정확한 레이어/차원/헤드 수는 `train.ipynb` 내 모델 빌드 셀 정의를 “단일 소스 오브 트루스”로 한다.

---

## 학습(Training)

### 손실/최적화

- **Loss**: 회귀 손실(MSE/MAE 계열 중 노트북 정의 사용)
- **Optimizer**: Adam 계열(학습률은 노트북 설정값 사용)

### 콜백

일반적으로 아래 콜백을 사용한다(노트북 구현 기준).

- **EarlyStopping**: 검증 성능 개선이 없으면 조기 종료
- **ModelCheckpoint**: 최고 성능 모델 가중치 저장
- (선택) ReduceLROnPlateau: 정체 시 학습률 감소

---

## 평가(Evaluation)

### 예측값 정렬(시점 정합)

예측은 “\(horizon\)일 뒤” 값이므로, 실제값과 비교할 때는 **실제값도 horizon만큼 shift**해서 같은 타임스탬프 기준으로 맞춘다.

예:

- `pred[t]` = \(t\) 시점에서 생성한 “\(t+h\)” 예측
- `actual[t]` = 실제값을 `shift(-h)` 해서 \(t+h\) 값을 \(t\)에 맞춰 비교

### 주요 지표

프로젝트에서 쓰는 대표 지표는 아래를 전제로 한다.

- **MAPE(%)**:
  - \( \text{MAPE} = \text{mean}(|(y - \hat{y}) / y|) \times 100 \)
- **정확도(%)**:
  - \( \text{Accuracy} = 100 - \text{MAPE} \)
- **상승확률(%)**:
  - \( (\hat{y} - \text{current}) / \text{current} \times 100 \)

> 0에 가까운 실제값에서 MAPE가 불안정해질 수 있으므로, 필요 시 분모 하한(epsilon) 등을 둘지 검토한다.

---

## 저장 산출물(Artifacts) & 버전 관리

학습 1회 완료 시, 모델 디렉토리에 아래 산출물을 저장한다(버전 경로는 실행 환경에 따라 다름).

예: `predict_model/model/v7_260511_최근30일_validation_주기5일/`

- **모델 파일**: `best_checkpoint.keras` 또는 `*.keras`
- **스케일러**:
  - `stock_scaler.pkl` (주가)
  - `econ_scaler.pkl` (경제지표)
- **메타 정보**: `model_meta.json`
  - `lookback`, `forecast_horizon`, `target_columns`, (및 기타 학습 설정)

### 메타 정보의 목적

- 추론/평가 단계에서 “학습 당시와 동일한 입력 정의(lookback/horizon/컬럼)”를 강제
- 운영 중 모델이 바뀌어도, 저장된 메타를 통해 호환성 검증 가능

---

## 추론(Inference) 입력/출력 규격

### 입력

추론은 학습과 동일하게, 최신 기준으로 아래 입력을 만든다.

- 최근 `LOOKBACK` 거래일의
  - 50종목 종가 시퀀스
  - 경제지표 시퀀스
- 학습 때 저장한 스케일러로 정규화 후 모델에 입력

### 출력

- 모델 출력: 50개 종목의 정규화된 예측값
- 역정규화 후 실제 가격 단위로 복원
- 날짜별로 DB(`predicted_stocks`)에 저장 및 후처리 지표 계산

---

## Horizon(예측일수) 변경 가이드

`FORECAST_HORIZON`은 **학습 데이터셋 생성(y 생성 위치)** 과 **평가 시 shift**, **메타 저장/추론 호환성**에 모두 영향이 있다.

- 수정 위치: `predict_model/train/train.ipynb` 상단 “실행 설정 변수” 셀의 `FORECAST_HORIZON`
- 권장: horizon을 바꾸면 **반드시 재학습**하고, 새로운 버전 디렉토리에 산출물을 저장한다.

---

## 운영 체크리스트(실수 방지)

- **컬럼 변경**(종목 추가/삭제, 경제지표 추가/삭제) 시:
  - `TARGET_COLUMNS`, `ECONOMIC_FEATURES` 갱신
  - 스케일러/메타/모델 재생성(재학습) 필수
- **horizon/lookback 변경** 시:
  - 모델/스케일러/메타 모두 재생성(재학습) 필수
- **추론 시 호환성**:
  - `model_meta.json`의 `lookback`, `forecast_horizon`, `target_columns`와
    운영 데이터의 컬럼/길이가 일치해야 함

