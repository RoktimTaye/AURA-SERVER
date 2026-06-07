
import os
import logging
import joblib
import pandas as pd
from typing import Any
import glob
from datetime import datetime, UTC
from prophet import Prophet
from sqlalchemy import inspect
from ..database import SessionLocal, engine
from .. import models

# Suppress Prophet and CmdStanPy logs
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
MIN_DATA_POINTS = 2 
MODELS_DIR = os.path.join("app", "ml", "models_district")
os.makedirs(MODELS_DIR, exist_ok=True)

def generate_fallback_forecast(df, item_id, district_name):
    """
    Fallback using basic statistics when Prophet fails.
    """
    try:
        last_price = float(df['y'].iloc[-1])
        if len(df) >= 2:
            recent_diff = float(df['y'].iloc[-1] - df['y'].iloc[0])
            daily_trend = recent_diff / len(df)
        else:
            daily_trend = 0
            
        last_date = pd.to_datetime(df['ds'].iloc[-1]).tz_localize(None)
        
        results = []
        for i in range(1, 8):
            target_date = (last_date + pd.Timedelta(days=i)).to_pydatetime()
            predicted = last_price + (daily_trend * i)
            predicted = max(0.1, predicted)
            
            results.append({
                "item_id": item_id,
                "district": district_name,
                "location_id": None, # District level
                "target_date": target_date,
                "predicted_price": round(float(predicted), 2),
                "yhat_lower": round(float(predicted * 0.9), 2),
                "yhat_upper": round(float(predicted * 1.1), 2),
                "trend": "UP" if daily_trend > 0.01 else "DOWN" if daily_trend < -0.01 else "STABLE",
                "created_at": datetime.now(UTC).replace(tzinfo=None)
            })
        return results
    except Exception:
        logger.error(f"Fallback failed for {item_id} in {district_name}")
        return None

def train_single_model(item_id, district_name, data_list):
    """
    Attempts Prophet training at District level, with fallback logic.
    """
    df = pd.DataFrame(data_list, columns=['y', 'ds'])
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    
    try:
        # District level usually provides > 10 points more often
        if len(df) >= 10:
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=False,
                yearly_seasonality=False,
                interval_width=0.95
            )
            model.fit(df)
            
            # Save the brain (District level)
            safe_district = str(district_name).replace(" ", "_").replace("/", "_")
            model_path = os.path.join(MODELS_DIR, f"brain_{item_id}_{safe_district}.joblib")
            joblib.dump(model, model_path)
            
            future = model.make_future_dataframe(periods=7)
            forecast = model.predict(future).tail(7)
            
            results = []
            for _, row in forecast.iterrows():
                results.append({
                    "item_id": item_id,
                    "district": district_name,
                    "location_id": None,
                    "target_date": row['ds'].to_pydatetime(),
                    "predicted_price": round(float(row['yhat']), 2),
                    "yhat_lower": round(float(row['yhat_lower']), 2),
                    "yhat_upper": round(float(row['yhat_upper']), 2),
                    "trend": "STABLE",
                    "created_at": datetime.now(UTC).replace(tzinfo=None)
                })
            return results
    except Exception:
        logger.warning(f"Prophet failed for {item_id} in {district_name}, falling back...")
    
    return generate_fallback_forecast(df, item_id, district_name)

def run_ml_pipeline():
    logger.info("🚀 Starting District-Level ML Pipeline (V1)...")
    
    db = SessionLocal()
    try:
        # 1. FETCH DATA (Joined with Location to get District)
        logger.info("📥 Fetching historical price data by District...")
        query = db.query(
            models.PriceEntry.item_id,
            models.Location.district,
            models.PriceEntry.price,
            models.PriceEntry.timestamp
        ).join(models.Location).filter(models.PriceEntry.status == "APPROVED")
        
        all_data = pd.read_sql(query.statement, engine)
        
        if all_data.empty:
            logger.warning("⚠️ No data found.")
            return

        # Sort data to ensure chronological order for fallback trend logic
        all_data = all_data.sort_values(by='timestamp')

        # 2. GROUP BY DISTRICT
        groups = all_data.groupby(['item_id', 'district'])
        tasks = []
        for key, group in groups:
            if isinstance(key, tuple) and len(key) == 2:
                # Cast to Any to satisfy the type checker for int() constructor
                item_id: Any = key[0]
                district_name = key[1]
                if len(group) >= MIN_DATA_POINTS:
                    data_list = group[['price', 'timestamp']].values.tolist()
                    tasks.append((int(item_id), district_name, data_list))
        
        logger.info(f"✅ Found {len(tasks)} Item-District pairs to forecast.")

        # 3. SEQUENTIAL PROCESSING
        all_forecasts = []
        completed = 0
        for tid, dname, data in tasks:
            result = train_single_model(tid, dname, data)
            if result:
                all_forecasts.extend(result)
            completed += 1
            if completed % 50 == 0 or completed == len(tasks):
                logger.info(f"Progress: {completed}/{len(tasks)} processed...")

        # 4. ATOMIC SWAP
        if all_forecasts:
            logger.info(f"💾 Updating database with {len(all_forecasts)} district forecast rows...")
            try:
                # Clean slate
                db.query(models.Forecast).delete(synchronize_session=False)
                # Bulk insert
                # Use inspect to satisfy type checkers requiring a Mapper
                db.bulk_insert_mappings(inspect(models.Forecast), all_forecasts)
                db.commit()

                # Cleanup joblib files to save memory and reduce server load
                for f in glob.glob(os.path.join(MODELS_DIR, "*.joblib")):
                    try:
                        os.remove(f)
                    except Exception as e:
                        pass

                logger.info("✨ District Pipeline Complete!")
            except Exception:
                db.rollback()
                logger.error("❌ DB Update failed")
        else:
            logger.warning("⚠️ No forecasts generated.")

    except Exception as e:
        logger.error(f"💥 Pipeline Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_ml_pipeline()
