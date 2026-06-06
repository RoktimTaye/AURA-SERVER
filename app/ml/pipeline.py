import logging
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

import numpy as np
import pandas as pd
from prophet import Prophet
from sqlalchemy import inspect, text

from .. import models
from ..database import SessionLocal, engine

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

FORECAST_DAYS = 7
MIN_DATA_POINTS = 10
PROPHET_MIN_POINTS = 30
VALIDATION_DAYS = 7
MAX_WORKERS = max(1, min((os.cpu_count() or 2) - 1, 6))
PRICE_SPIKE_MULTIPLIER = 10.0
FORECAST_INDEX_NAME = "idx_forecast_item_district_date"


@dataclass
class ModelResult:
    item_id: int
    district: str
    method: str
    forecasts: list[dict[str, Any]]
    metrics: dict[str, float | bool | None]
    input_rows: int
    cleaned_rows: int
    warning: str | None = None


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _to_naive_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _trend_label(first_price: float, last_price: float, days: int) -> str:
    if days <= 0:
        return "STABLE"
    daily_change = (last_price - first_price) / days
    if daily_change > 0.01:
        return "UP"
    if daily_change < -0.01:
        return "DOWN"
    return "STABLE"


def preprocess_price_history(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared train/serve-style transformation for item-district price history.

    This follows the TensorFlow Transform principle used in the project docs: keep
    one reusable transform boundary so validation and final training see the same
    cleaned representation. It intentionally stays in pandas because the server
    does not depend on TensorFlow/TFX.
    """
    if raw_df.empty:
        return pd.DataFrame(columns=["ds", "y"])

    df = raw_df[["ds", "y"]].copy()
    df["ds"] = pd.to_datetime(df["ds"], errors="coerce", utc=True).dt.tz_convert(None)
    df["ds"] = df["ds"].dt.normalize()
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna(subset=["ds", "y"])
    df = df[np.isfinite(df["y"])]
    df = df[df["y"] > 0]

    if df.empty:
        return pd.DataFrame(columns=["ds", "y"])

    df = df.groupby("ds", as_index=False)["y"].median().sort_values("ds")

    if len(df) >= 3:
        median_price = float(df["y"].median())
        absolute_deviation = (df["y"] - median_price).abs()
        mad = float(absolute_deviation.median())

        if mad > 0:
            modified_z = 0.6745 * absolute_deviation / mad
            df = df[modified_z <= 6.0]
        elif median_price > 0:
            lower = median_price / PRICE_SPIKE_MULTIPLIER
            upper = median_price * PRICE_SPIKE_MULTIPLIER
            df = df[(df["y"] >= lower) & (df["y"] <= upper)]

    return df.sort_values("ds").reset_index(drop=True)


def calculate_metrics(
    actual: Iterable[float],
    predicted: Iterable[float],
    baseline: Iterable[float],
) -> dict[str, float | bool | None]:
    actual_arr = np.asarray(list(actual), dtype=float)
    predicted_arr = np.asarray(list(predicted), dtype=float)
    baseline_arr = np.asarray(list(baseline), dtype=float)

    if len(actual_arr) == 0 or len(actual_arr) != len(predicted_arr):
        return {
            "mae": None,
            "rmse": None,
            "mape": None,
            "baseline_mae": None,
            "baseline_rmse": None,
            "baseline_mape": None,
            "beats_baseline": False,
        }

    error = actual_arr - predicted_arr
    baseline_error = actual_arr - baseline_arr
    non_zero = actual_arr != 0

    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error**2)))
    baseline_mae = float(np.mean(np.abs(baseline_error)))
    baseline_rmse = float(np.sqrt(np.mean(baseline_error**2)))

    mape = None
    baseline_mape = None
    if np.any(non_zero):
        mape = float(np.mean(np.abs(error[non_zero] / actual_arr[non_zero])) * 100)
        baseline_mape = float(
            np.mean(np.abs(baseline_error[non_zero] / actual_arr[non_zero])) * 100
        )

    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape": round(mape, 4) if mape is not None else None,
        "baseline_mae": round(baseline_mae, 4),
        "baseline_rmse": round(baseline_rmse, 4),
        "baseline_mape": round(baseline_mape, 4) if baseline_mape is not None else None,
        "beats_baseline": mae <= baseline_mae,
    }


def _build_forecast_row(
    item_id: int,
    district_name: str,
    target_date: pd.Timestamp | datetime,
    predicted_price: float,
    lower: float,
    upper: float,
    trend: str,
) -> dict[str, Any]:
    predicted_price = max(0.1, float(predicted_price))
    lower = max(0.1, float(lower))
    upper = max(lower, float(upper))
    return {
        "item_id": int(item_id),
        "district": str(district_name),
        "location_id": None,
        "target_date": _to_naive_timestamp(target_date).to_pydatetime(),
        "predicted_price": round(predicted_price, 2),
        "yhat_lower": round(lower, 2),
        "yhat_upper": round(upper, 2),
        "trend": trend,
        "created_at": _now_naive_utc(),
    }


def generate_fallback_forecast(
    df: pd.DataFrame,
    item_id: int,
    district_name: str,
    periods: int = FORECAST_DAYS,
) -> list[dict[str, Any]]:
    if df.empty:
        return []

    clean_df = preprocess_price_history(df) if set(["ds", "y"]).issubset(df.columns) else df
    if clean_df.empty:
        return []

    first_date = pd.Timestamp(clean_df["ds"].iloc[0])
    last_date = pd.Timestamp(clean_df["ds"].iloc[-1])
    first_price = float(clean_df["y"].iloc[0])
    last_price = float(clean_df["y"].iloc[-1])
    days = max((last_date - first_date).days, 1)
    daily_trend = (last_price - first_price) / days
    trend = _trend_label(first_price, last_price, days)

    forecasts = []
    for offset in range(1, periods + 1):
        predicted = max(0.1, last_price + daily_trend * offset)
        target_date = last_date + pd.Timedelta(days=offset)
        forecasts.append(
            _build_forecast_row(
                item_id=item_id,
                district_name=district_name,
                target_date=target_date,
                predicted_price=predicted,
                lower=predicted * 0.9,
                upper=predicted * 1.1,
                trend=trend,
            )
        )
    return forecasts


def _make_prophet_model(interval_width: float = 0.9) -> Prophet:
    return Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        interval_width=interval_width,
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10.0,
    )


def _forecast_with_prophet(
    train_df: pd.DataFrame,
    item_id: int,
    district_name: str,
    periods: int,
) -> list[dict[str, Any]]:
    model = _make_prophet_model()
    model.fit(train_df)
    future = model.make_future_dataframe(periods=periods, freq="D")
    forecast = model.predict(future).tail(periods)

    first_price = float(train_df["y"].iloc[0])
    last_price = float(train_df["y"].iloc[-1])
    first_date = pd.Timestamp(train_df["ds"].iloc[0])
    last_date = pd.Timestamp(train_df["ds"].iloc[-1])
    trend = _trend_label(first_price, last_price, max((last_date - first_date).days, 1))

    return [
        _build_forecast_row(
            item_id=item_id,
            district_name=district_name,
            target_date=row["ds"],
            predicted_price=row["yhat"],
            lower=row["yhat_lower"],
            upper=row["yhat_upper"],
            trend=trend,
        )
        for _, row in forecast.iterrows()
    ]


def _validate_prophet_against_baseline(clean_df: pd.DataFrame) -> dict[str, float | bool | None]:
    if len(clean_df) < PROPHET_MIN_POINTS + VALIDATION_DAYS:
        return {
            "mae": None,
            "rmse": None,
            "mape": None,
            "baseline_mae": None,
            "baseline_rmse": None,
            "baseline_mape": None,
            "beats_baseline": None,
        }

    train_df = clean_df.iloc[:-VALIDATION_DAYS].copy()
    test_df = clean_df.iloc[-VALIDATION_DAYS:].copy()
    model = _make_prophet_model()
    model.fit(train_df)
    future = pd.DataFrame({"ds": test_df["ds"]})
    validation_forecast = model.predict(future)
    predicted = validation_forecast["yhat"].tolist()
    baseline = [float(train_df["y"].iloc[-1])] * len(test_df)
    return calculate_metrics(test_df["y"].tolist(), predicted, baseline)


def train_single_model(item_id: int, district_name: str, data_list: list[list[Any]]) -> ModelResult:
    raw_df = pd.DataFrame(data_list, columns=["y", "ds"])
    clean_df = preprocess_price_history(raw_df)

    if len(clean_df) < MIN_DATA_POINTS:
        forecasts = generate_fallback_forecast(clean_df, item_id, district_name)
        return ModelResult(
            item_id=int(item_id),
            district=str(district_name),
            method="fallback",
            forecasts=forecasts,
            metrics={},
            input_rows=len(raw_df),
            cleaned_rows=len(clean_df),
            warning="insufficient_clean_history",
        )

    if len(clean_df) < PROPHET_MIN_POINTS:
        forecasts = generate_fallback_forecast(clean_df, item_id, district_name)
        return ModelResult(
            item_id=int(item_id),
            district=str(district_name),
            method="fallback",
            forecasts=forecasts,
            metrics={},
            input_rows=len(raw_df),
            cleaned_rows=len(clean_df),
            warning="below_prophet_threshold",
        )

    try:
        metrics = _validate_prophet_against_baseline(clean_df)
        forecasts = _forecast_with_prophet(clean_df, item_id, district_name, FORECAST_DAYS)
        return ModelResult(
            item_id=int(item_id),
            district=str(district_name),
            method="prophet",
            forecasts=forecasts,
            metrics=metrics,
            input_rows=len(raw_df),
            cleaned_rows=len(clean_df),
        )
    except Exception as exc:
        logger.warning("Prophet failed for item=%s district=%s: %s", item_id, district_name, exc)
        forecasts = generate_fallback_forecast(clean_df, item_id, district_name)
        return ModelResult(
            item_id=int(item_id),
            district=str(district_name),
            method="fallback_after_prophet_error",
            forecasts=forecasts,
            metrics={},
            input_rows=len(raw_df),
            cleaned_rows=len(clean_df),
            warning=str(exc),
        )


def _prepare_tasks(all_data: pd.DataFrame) -> list[tuple[int, str, list[list[Any]]]]:
    all_data = all_data.dropna(subset=["item_id", "district", "price", "timestamp"])
    all_data = all_data.sort_values("timestamp")
    tasks = []
    for key, group in all_data.groupby(["item_id", "district"]):
        if not isinstance(key, tuple) or len(key) != 2:
            continue
        item_id, district_name = key
        data_list = group[["price", "timestamp"]].values.tolist()
        tasks.append((int(item_id), str(district_name), data_list))
    return tasks


def ensure_forecast_index() -> None:
    sql = (
        f"CREATE INDEX IF NOT EXISTS {FORECAST_INDEX_NAME} "
        "ON forecasts (item_id, district, target_date);"
    )
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()


def _run_tasks(tasks: list[tuple[int, str, list[list[Any]]]], parallel: bool) -> list[ModelResult]:
    if not parallel or len(tasks) <= 1:
        return [train_single_model(item_id, district, data) for item_id, district, data in tasks]

    results: list[ModelResult] = []
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(train_single_model, item_id, district, data): (item_id, district)
            for item_id, district, data in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            item_id, district = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                logger.warning("Worker failed for item=%s district=%s: %s", item_id, district, exc)
            if completed % 50 == 0 or completed == len(tasks):
                logger.info("Forecast progress: %s/%s groups processed", completed, len(tasks))
    return results


def run_ml_pipeline(parallel: bool = True) -> None:
    logger.info("Starting production district-level ML pipeline")
    db = SessionLocal()
    try:
        ensure_forecast_index()
        query = db.query(
            models.PriceEntry.item_id,
            models.Location.district,
            models.PriceEntry.price,
            models.PriceEntry.timestamp,
        ).join(models.Location).filter(models.PriceEntry.status == "APPROVED")

        all_data = pd.read_sql(query.statement, engine)
        if all_data.empty:
            logger.warning("No approved historical price data found")
            return

        tasks = _prepare_tasks(all_data)
        logger.info("Prepared %s item-district groups for forecasting", len(tasks))

        results = _run_tasks(tasks, parallel=parallel)
        all_forecasts = [row for result in results for row in result.forecasts]

        prophet_count = sum(1 for result in results if result.method == "prophet")
        fallback_count = len(results) - prophet_count
        logger.info(
            "Generated %s forecast rows from %s groups; prophet=%s fallback=%s",
            len(all_forecasts),
            len(results),
            prophet_count,
            fallback_count,
        )

        if not all_forecasts:
            logger.warning("No forecasts generated")
            return

        db.query(models.Forecast).delete(synchronize_session=False)
        db.bulk_insert_mappings(inspect(models.Forecast), all_forecasts)
        db.commit()
        logger.info("Forecast table updated successfully")
    except Exception as exc:
        db.rollback()
        logger.error("Production pipeline failed: %s", exc)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_ml_pipeline(parallel=True)
