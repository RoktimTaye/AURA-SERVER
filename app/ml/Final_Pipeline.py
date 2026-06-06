import os
import logging
import joblib
import itertools
import pandas as pd
import numpy as np
from typing import Any, List, Dict
from datetime import datetime, UTC
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from prophet import Prophet
from sqlalchemy import inspect, text
import warnings
import sys

# System Path setup to ensure absolute imports work when run as a script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from app.database import SessionLocal, engine
from app import models

# Suppress heavy logs for production output
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration based on Technical Context
MIN_DATA_POINTS = 10 
Z_SCORE_THRESHOLD = 3.0
FORECAST_HORIZON_DAYS = 7
MODELS_DIR = os.path.join("app", "ml", "models_district")
os.makedirs(MODELS_DIR, exist_ok=True)

# --- PDF ENHANCEMENT: TFX PREPROCESSING ---

def preprocess_tfx_style(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans data and applies feature scaling to prevent skew.
    Following TFX principles of data validation and transformation.
    """
    df = df.sort_values('ds').copy()
    
    # 1. Outlier Removal (Z-Score)
    # acts as the "Shield" for the forecasting model
    if len(df) > 5:
        m, s = df['y'].mean(), df['y'].std()
        if s > 0:
            df = df[((df['y'] - m) / s).abs() <= Z_SCORE_THRESHOLD]

    # 2. Log Transformation (Normalization)
    # Prices often show exponential growth; log-scaling makes trends linear
    # This prevents the model from being overwhelmed by large price values.
    df['y'] = np.log1p(df['y'])
    
    return df

# --- PDF ENHANCEMENT: SNITCH AI EVALUATION ---

def evaluate_and_tune(df: pd.DataFrame) -> Dict:
    """
    Uses RMSE on a sequential Train/Test split to find the most accurate parameters.
    Ensures model quality over simple accuracy (Snitch AI approach).
    """
    if len(df) < 15:
        # Return stable defaults if dataset is too small for a split
        return {'changepoint_prior_scale': 0.05, 'seasonality_prior_scale': 10.0}

    # Hold out the last 7 points as a test set
    train_df = df.iloc[:-7]
    test_df = df.iloc[-7:]
    
    param_grid = {
        'changepoint_prior_scale': [0.01, 0.1],
        'seasonality_prior_scale': [1.0, 10.0]
    }
    all_params = [dict(zip(param_grid.keys(), v)) for v in itertools.product(*param_grid.values())]
    
    best_rmse, best_params = float('inf'), {'changepoint_prior_scale': 0.05, 'seasonality_prior_scale': 10.0}
    
    for params in all_params:
        try:
            m = Prophet(yearly_seasonality=True, **params).fit(train_df)
            forecast = m.predict(pd.DataFrame({'ds': test_df['ds']}))
            
            # Evaluate using RMSE on original price scale (expm1)
            rmse = np.sqrt(np.mean((np.expm1(test_df['y'].values) - np.expm1(forecast['yhat'].values))**2))
            if rmse < best_rmse:
                best_rmse = rmse
                best_params = params
        except Exception:
            continue
            
    return best_params

# --- THE WORKER UNIT ---

def process_district_task(item_id: int, district: str):
    """
    Isolated worker function that uses the COMPOSITE INDEX to fetch its own data subset.
    This minimizes database locking and maximizes throughput.
    """
    db = SessionLocal()
    try:
        # STEP 1: INDEXED FETCH
        # This query hits the (status, item_id, location_id) index perfectly for instant retrieval
        query = db.query(models.PriceEntry.price.label('y'), models.PriceEntry.timestamp.label('ds'))\
                  .join(models.Location)\
                  .filter(models.PriceEntry.status == "APPROVED",
                          models.PriceEntry.item_id == item_id,
                          models.Location.district == district).statement
        
        df = pd.read_sql(query, engine)
        if len(df) < MIN_DATA_POINTS: return None

        # STEP 2: PREPROCESS (TFX STYLE)
        df = preprocess_tfx_style(df)

        # STEP 3: TUNE & TRAIN (SNITCH AI STYLE)
        best_p = evaluate_and_tune(df)
        
        # Additive model with daily/weekly/yearly seasonality as per context
        model = Prophet(
            yearly_seasonality=True, 
            weekly_seasonality=True, 
            daily_seasonality=True,
            interval_width=0.95, 
            **best_p
        ).fit(df)
        
        # Persist the trained model "brain"
        safe_district = str(district).replace(" ", "_").replace("/", "_")
        model_path = os.path.join(MODELS_DIR, f"brain_{item_id}_{safe_district}.joblib")
        joblib.dump(model, model_path)
        
        # STEP 4: FORECAST & INVERT LOG
        future = model.make_future_dataframe(periods=FORECAST_HORIZON_DAYS)
        forecast = model.predict(future).tail(FORECAST_HORIZON_DAYS)
        
        results = []
        for _, row in forecast.iterrows():
            results.append({
                "item_id": item_id, 
                "district": district, 
                "location_id": None,
                "target_date": row['ds'].to_pydatetime(),
                "predicted_price": round(float(np.expm1(row['yhat'])), 2), # Invert log(x+1)
                "yhat_lower": round(float(np.expm1(row['yhat_lower'])), 2),
                "yhat_upper": round(float(np.expm1(row['yhat_upper'])), 2),
                "trend": "STABLE", 
                "created_at": datetime.now(UTC).replace(tzinfo=None)
            })
        return results
    except Exception:
        return None
    finally:
        db.close()

# --- THE PIPELINE ---

def run_ml_pipeline():
    logger.info("🚀 Starting Composite-Index Optimized Production ML Pipeline")
    db = SessionLocal()
    
    try:
        # 1. IDENTIFY WORKLOAD (Very fast using index metadata)
        logger.info("🔍 Identifying active Item-District pairs...")
        pairs = db.execute(text("""
            SELECT DISTINCT pe.item_id, l.district 
            FROM price_entries pe 
            JOIN locations l ON pe.location_id = l.id 
            WHERE pe.status = 'APPROVED'
        """)).fetchall()
        
        tasks = [(int(p[0]), p[1]) for p in pairs]
        logger.info(f"✅ Found {len(tasks)} tasks. Launching High-Throughput Engine...")

        # 2. PARALLEL EXECUTION (Utilizes all CPU Cores)
        all_forecasts = []
        with ProcessPoolExecutor(max_workers=max(1, cpu_count() - 1)) as executor:
            futures = [executor.submit(process_district_task, tid, dname) for tid, dname in tasks]
            
            for i, f in enumerate(futures):
                res = f.result()
                if res: all_forecasts.extend(res)
                if (i+1) % 50 == 0: logger.info(f"Progress: {i+1}/{len(tasks)} processed")

        # 3. ATOMIC DB UPDATE
        if all_forecasts:
            logger.info(f"💾 Saving {len(all_forecasts)} predictions to database...")
            # Use synchronize_session=False for high performance delete
            db.query(models.Forecast).delete(synchronize_session=False)
            db.bulk_insert_mappings(inspect(models.Forecast), all_forecasts)
            db.commit()
            
            print("\n" + "="*50)
            print("✨ PRODUCTION PIPELINE COMPLETE")
            print(f"   Items Processed:   {len(tasks)}")
            print(f"   Predictions Saved: {len(all_forecasts)}")
            print("="*50 + "\n")
        else:
            logger.warning("No forecasts generated. Check data points thresholds.")

    except Exception as e:
        logger.error(f"💥 Critical Pipeline Failure: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_ml_pipeline()
