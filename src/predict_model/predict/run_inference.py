"""
학습 산출물(predict_model/model/<버전>/)을 불러와 추론 후 Supabase를 갱신합니다.

  uv run python predict_model/predict/run_inference.py

모델 경로: .env 의 PREDICT_MODEL_DIR → app.core.config.settings.predict_model_path 와 동일.
  예: PREDICT_MODEL_DIR=predict_model/model/v7_260511_최근30일_validation_주기5일
  CLI --model-dir 가 있으면 env 보다 우선합니다.

환경 변수: SUPABASE_URL, SUPABASE_SERVICE_KEY(권장) 또는 SUPABASE_KEY
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

# 직접 실행 시 (`python predict_model/predict/run_inference.py`) 프로젝트 루트가 path 에 없음
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.metrics import mean_absolute_error, mean_squared_error
from supabase import Client, create_client
from tensorflow.keras.models import load_model


def _repo_root() -> Path:
    return _REPO_ROOT


def resolve_model_dir(cli_path: Path | None) -> Path:
    """--model-dir 이 있으면 그것만 사용. 없으면 .env 의 PREDICT_MODEL_DIR (app.core.config 와 동일 해석)."""
    if cli_path is not None:
        return cli_path.resolve()
    # main() 에서 _load_env() 후 호출됨 → os.environ 반영된 뒤 settings 로드
    from app.core.config import settings

    return settings.predict_model_path


def _load_env() -> None:
    # 프로젝트 루트 .env 가 cwd 와 무관하게 적용되도록, 기존 값보다 우선(override)
    load_dotenv(_repo_root() / ".env", override=True)


def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 및 SUPABASE_SERVICE_KEY(또는 SUPABASE_KEY)를 .env에 설정하세요."
        )
    return create_client(url, key)


def get_all_rows(supabase: Client, table_name: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    limit = 1000
    while True:
        resp = (
            supabase.table(table_name)
            .select("*")
            .order("날짜", desc=False)
            .limit(limit)
            .offset(offset)
            .execute()
        )
        chunk = resp.data or []
        if not chunk:
            break
        rows.extend(chunk)
        offset += limit
    return rows


def load_stock_frame(supabase: Client) -> pd.DataFrame:
    all_data = get_all_rows(supabase, "economic_and_stock_data")
    if not all_data:
        raise RuntimeError("economic_and_stock_data 에서 가져온 행이 없습니다.")
    df = pd.DataFrame(all_data)
    df["날짜"] = pd.to_datetime(df["날짜"])
    df.sort_values(by="날짜", inplace=True)
    df = df.ffill().bfill()
    exclude = ["날짜"]
    numeric = [c for c in df.columns if c not in exclude]
    df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
    nan_ratios = df[numeric].isna().mean()
    valid = [c for c in numeric if nan_ratios[c] < 1.0]
    df.dropna(subset=valid, inplace=True)
    return df


def load_model_dir(model_dir: Path) -> tuple:
    meta_path = model_dir / "model_meta.json"
    model_path = model_dir / "transformer_stock.keras"
    stock_pkl = model_dir / "stock_scaler.pkl"
    econ_pkl = model_dir / "econ_scaler.pkl"
    for p in (meta_path, model_path, stock_pkl, econ_pkl):
        if not p.is_file():
            raise FileNotFoundError(f"필수 파일이 없습니다: {p}")
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    stock_scaler = joblib.load(stock_pkl)
    econ_scaler = joblib.load(econ_pkl)
    model = load_model(model_path)
    return model, stock_scaler, econ_scaler, meta


def run_prediction_pipeline(
    data: pd.DataFrame,
    model,
    stock_scaler,
    econ_scaler,
    target_columns: list[str],
    economic_features: list[str],
    lookback: int,
    forecast_horizon: int,
) -> pd.DataFrame:
    missing = [c for c in target_columns + economic_features if c not in data.columns]
    if missing:
        raise ValueError(f"데이터에 없는 컬럼: {missing[:10]}{'...' if len(missing) > 10 else ''}")

    scaled = data.copy()
    scaled[target_columns] = stock_scaler.transform(data[target_columns])
    scaled[economic_features] = econ_scaler.transform(data[economic_features])

    xs, xe = [], []
    for i in range(lookback, len(scaled)):
        xs.append(scaled[target_columns].iloc[i - lookback : i].to_numpy())
        xe.append(scaled[economic_features].iloc[i - lookback : i].to_numpy())
    x_stock = np.array(xs)
    x_econ = np.array(xe)

    pred_scaled = model.predict([x_stock, x_econ], verbose=1)
    pred_actual = stock_scaler.inverse_transform(pred_scaled)
    pred_len = len(pred_actual)
    today_dates = data["날짜"].iloc[lookback : lookback + pred_len].values
    actual_end = min(lookback + pred_len, len(data))
    actual_full = data[target_columns].iloc[lookback:actual_end].values
    if actual_full.shape[0] < pred_len:
        pad = np.full((pred_len - actual_full.shape[0], len(target_columns)), np.nan)
        actual_full = np.vstack([actual_full, pad])

    out = pd.DataFrame({"날짜": today_dates})
    for idx, col in enumerate(target_columns):
        out[f"{col}_Predicted"] = pred_actual[:, idx]
        out[f"{col}_Actual"] = actual_full[:, idx]
    out["날짜"] = pd.to_datetime(out["날짜"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out


def _records_sanitize(df: pd.DataFrame) -> list[dict]:
    records = []
    for _, row in df.iterrows():
        rec = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                rec[k] = None
            else:
                rec[k] = v
        records.append(rec)
    return records


def save_predictions_to_db(supabase: Client, result_df: pd.DataFrame, chunk_size: int = 100) -> None:
    records = _records_sanitize(result_df)
    supabase.table("predicted_stocks").delete().neq("id", 0).execute()
    for i in range(0, len(records), chunk_size):
        supabase.table("predicted_stocks").insert(records[i : i + chunk_size]).execute()
    print(f"predicted_stocks: {len(records)}행 저장 완료")


def get_predictions_from_db(supabase: Client, chunk_size: int = 1000) -> pd.DataFrame:
    count_resp = supabase.table("predicted_stocks").select("id", count="exact").execute()
    total = count_resp.count or 0
    all_data: list[dict] = []
    for offset in range(0, total, chunk_size):
        resp = (
            supabase.table("predicted_stocks")
            .select("*")
            .order("날짜", desc=False)
            .limit(chunk_size)
            .offset(offset)
            .execute()
        )
        all_data.extend(resp.data or [])
    df = pd.DataFrame(all_data)
    if df.empty:
        raise RuntimeError("predicted_stocks 가 비어 있습니다.")
    df["날짜"] = pd.to_datetime(df["날짜"])
    return df


def evaluate_predictions(data: pd.DataFrame, target_columns: list[str], forecast_horizon: int) -> pd.DataFrame:
    metrics = []
    for col in target_columns:
        pc, ac = f"{col}_Predicted", f"{col}_Actual"
        if pc not in data.columns or ac not in data.columns:
            continue
        predicted = data[pc]
        actual = data[ac].shift(-forecast_horizon)
        valid = ~predicted.isna() & ~actual.isna()
        predicted = predicted[valid]
        actual = actual[valid]
        if len(predicted) == 0:
            continue
        mae = mean_absolute_error(actual, predicted)
        mse = mean_squared_error(actual, predicted)
        rmse = mse**0.5
        mape = (abs((actual - predicted) / actual).mean()) * 100
        accuracy = 100 - mape
        metrics.append(
            {
                "Stock": col,
                "MAE": mae,
                "MSE": mse,
                "RMSE": rmse,
                "MAPE (%)": mape,
                "Accuracy (%)": accuracy,
            }
        )
    return pd.DataFrame(metrics)


def analyze_rise_predictions(data: pd.DataFrame, target_columns: list[str]) -> pd.DataFrame:
    last_row = data.iloc[-1]
    results = []
    for col in target_columns:
        ac, pc = f"{col}_Actual", f"{col}_Predicted"
        last_a = last_row.get(ac, np.nan)
        last_p = last_row.get(pc, np.nan)
        if pd.notna(last_a) and pd.notna(last_p):
            rise = last_p > last_a
            rise_pct = ((last_p - last_a) / last_a) * 100
        else:
            rise = np.nan
            rise_pct = np.nan
        results.append(
            {
                "Stock": col,
                "Last Actual Price": last_a,
                "Predicted Future Price": last_p,
                "Predicted Rise": rise,
                "Rise Probability (%)": rise_pct,
            }
        )
    return pd.DataFrame(results)


def generate_recommendation(row: pd.Series) -> str:
    rise_prob = row.get("Rise Probability (%)", 0)
    predicted_rise = row.get("Predicted Rise", False)
    if pd.isna(rise_prob) or pd.isna(predicted_rise):
        return "No Data"
    if predicted_rise and rise_prob > 0:
        return "STRONG BUY" if rise_prob > 2 else "BUY"
    return "SELL"


def generate_analysis(row: pd.Series) -> str:
    name = row["Stock"]
    rise_prob = row.get("Rise Probability (%)", 0)
    predicted_rise = row.get("Predicted Rise", False)
    if pd.isna(rise_prob) or pd.isna(predicted_rise):
        return f"{name}: Not enough data"
    if predicted_rise:
        return f"{name} is expected to rise by about {rise_prob:.2f}%. Consider buying or holding."
    return f"{name} is expected to fall by about {-rise_prob:.2f}%. A cautious approach is recommended."


def dataframe_rows_to_jsonable_records(result_df: pd.DataFrame) -> list[dict]:
    """DB·JSON 직렬화에 맞춘 행 목록 (NaN/ numpy 스칼라 정규화)."""
    records: list[dict] = []
    for _, row in result_df.iterrows():
        rec: dict = {}
        for k, v in row.items():
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                rec[k] = None
            elif hasattr(v, "item"):
                rec[k] = v.item()
            else:
                rec[k] = v
        records.append(rec)
    return records


def save_analysis_to_db(supabase: Client, result_df: pd.DataFrame, chunk_size: int = 100) -> None:
    records = dataframe_rows_to_jsonable_records(result_df)
    supabase.table("stock_analysis_results").delete().neq("id", 0).execute()
    for i in range(0, len(records), chunk_size):
        supabase.table("stock_analysis_results").insert(records[i : i + chunk_size]).execute()
    print(f"stock_analysis_results: {len(records)}행 저장 완료")


def build_final_analysis(pred_df: pd.DataFrame, target_columns: list[str], forecast_horizon: int) -> pd.DataFrame:
    evaluation = evaluate_predictions(pred_df, target_columns, forecast_horizon)
    rise = analyze_rise_predictions(pred_df, target_columns)
    final = pd.merge(evaluation, rise, on="Stock", how="outer")
    final = final.sort_values(by="Rise Probability (%)", ascending=False)
    final["Recommendation"] = final.apply(generate_recommendation, axis=1)
    final["Analysis"] = final.apply(generate_analysis, axis=1)
    order = [
        "data_date",
        "Stock",
        "MAE",
        "MSE",
        "RMSE",
        "MAPE (%)",
        "Accuracy (%)",
        "Last Actual Price",
        "Predicted Future Price",
        "Predicted Rise",
        "Rise Probability (%)",
        "Recommendation",
        "Analysis",
    ]
    # data_date는 run_inference_and_save_to_db()에서 주입될 수 있다.
    cols = [c for c in order if c in final.columns]
    return final[cols]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Transformer 추론 및 DB 갱신")
    p.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="모델 디렉터리(미지정 시 .env 의 PREDICT_MODEL_DIR)",
    )
    p.add_argument(
        "--no-db",
        action="store_true",
        help="Supabase에서 데이터는 읽되, predicted_stocks / stock_analysis_results 에는 쓰지 않음",
    )
    return p.parse_args()


def run_inference_and_save_to_db(
    model_dir: Path | None = None,
    *,
    write_db: bool = True,
) -> dict:
    """
    저장된 모델(PREDICT_MODEL_DIR)로 추론 후 DB 갱신.
    스케줄러(경제 데이터 갱신 직후)에서 호출한다.

    Returns:
        success, model_dir, prediction_rows, analysis_rows (write_db 시),
        analysis_records (write_db 시 stock_analysis_results 에 해당하는 전체 행),
        write_db
    """
    _load_env()
    resolved = resolve_model_dir(model_dir)
    print(f"MODEL_DIR = {resolved}")

    model, stock_scaler, econ_scaler, meta = load_model_dir(resolved)
    target_columns = meta["target_columns"]
    economic_features = meta["economic_features"]
    lookback = int(meta["lookback"])
    forecast_horizon = int(meta["forecast_horizon"])

    supabase = get_supabase()
    print("economic_and_stock_data 로드 중...")
    data = load_stock_frame(supabase)
    print(f"행 수: {len(data)}")

    result_data = run_prediction_pipeline(
        data,
        model,
        stock_scaler,
        econ_scaler,
        target_columns,
        economic_features,
        lookback,
        forecast_horizon,
    )

    if not write_db:
        print(result_data.tail(5).to_string())
        print("\n(--no-db: DB 저장 생략)")
        return {
            "success": True,
            "write_db": False,
            "model_dir": str(resolved),
            "prediction_rows": len(result_data),
            "analysis_records": [],
        }

    save_predictions_to_db(supabase, result_data)

    pred_from_db = get_predictions_from_db(supabase)
    final = build_final_analysis(pred_from_db, target_columns, forecast_horizon)
    # 데이터 기준일: predicted_stocks(=경제/주가 데이터)의 최신 날짜를 stock_analysis_results에 함께 저장한다.
    # created_at(적재시각)과 분리해서, 프론트 그리드가 "DB에 저장된 기준일"을 그대로 표시할 수 있게 한다.
    try:
        data_date = None
        if "날짜" in pred_from_db.columns and len(pred_from_db) > 0:
            # pandas Timestamp / datetime.date 등 → YYYY-MM-DD 문자열로 정규화
            dd = pred_from_db["날짜"].max()
            data_date = dd.date().isoformat() if hasattr(dd, "date") else str(dd)
        if data_date:
            final["data_date"] = data_date
    except Exception as e:
        print(f"[WARN] data_date 계산 실패 — created_at만 사용: {e}")
    analysis_records = dataframe_rows_to_jsonable_records(final)
    save_analysis_to_db(supabase, final)
    print("\n=== 완료: predicted_stocks + stock_analysis_results 갱신 ===")
    print(final.head(10).to_string(index=False))
    return {
        "success": True,
        "write_db": True,
        "model_dir": str(resolved),
        "prediction_rows": len(result_data),
        "analysis_rows": len(final),
        "analysis_records": analysis_records,
    }


def main() -> None:
    _load_env()
    args = parse_args()
    try:
        run_inference_and_save_to_db(args.model_dir, write_db=not args.no_db)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
