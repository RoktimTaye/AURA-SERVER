import os
import logging
import joblib
import glob
from datetime import datetime, UTC
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from sqlalchemy import inspect

from .data_loader import DataLoader
from .preprocessor import Preprocessor
from .trainer import ModelTrainer
from app.database import SessionLocal
from app import models

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join("app", "ml", "models_modular")
os.makedirs(MODELS_DIR, exist_ok=True)

def process_single_task(item_id, district, fast_mode=True, use_db=True):
    """
    Worker function for parallel processing.
    """
    loader = DataLoader(use_db=use_db)
    preprocessor = Preprocessor()
    trainer = ModelTrainer(fast_mode=fast_mode)

    # 1. Load
    df = loader.load_data(item_id, district)
    if len(df) < 10:
        return None

    # 2. Preprocess
    df_clean = preprocessor.process(df)
    if len(df_clean) < 10:
        return None

    # 3. Tune & Train
    try:
        model, best_params = trainer.tune_and_train(df_clean)
        
        # 4. Save Model
        safe_district = str(district).replace(" ", "_").replace("/", "_")
        model_path = os.path.join(MODELS_DIR, f"model_{item_id}_{safe_district}.joblib")
        joblib.dump(model, model_path)

        # Calculate a realistic minimum floor based on historical data.
        # We allow the prediction to drop a maximum of 30% below the historical all-time low.
        historical_min_log = df_clean['y'].min()
        historical_min_price = float(preprocessor.inverse_transform(historical_min_log))
        realistic_floor = max(1.0, historical_min_price * 0.7)

        # 5. Forecast
        future = model.make_future_dataframe(periods=7)
        forecast = model.predict(future).tail(7)

        # 6. Format results
        results = []
        for _, row in forecast.iterrows():
            pred_price = round(float(preprocessor.inverse_transform(row['yhat'])), 2)
            lower = round(float(preprocessor.inverse_transform(row['yhat_lower'])), 2)
            upper = round(float(preprocessor.inverse_transform(row['yhat_upper'])), 2)
            
            # Prevent unrealistic price crashes by clamping to the dynamic historical floor
            pred_price = max(realistic_floor, pred_price)
            lower = max(realistic_floor, lower)
            upper = max(realistic_floor, upper)

            results.append({
                "item_id": item_id,
                "district": district,
                "location_id": None,
                "target_date": row['ds'].to_pydatetime(),
                "predicted_price": pred_price,
                "yhat_lower": lower,
                "yhat_upper": upper,
                "trend": "STABLE",
                "created_at": datetime.now(UTC).replace(tzinfo=None)
            })
        return results
    except Exception as e:
        logger.error(f"Error processing task {item_id} - {district}: {e}")
        return None

class MLPipeline:
    def __init__(self, fast_mode=True):
        self.loader = DataLoader()
        self.fast_mode = fast_mode

    def run(self):
        logger.info("Starting Modular ML Pipeline...")
        
        # 1. Get pairs
        pairs = self.loader.get_active_pairs()
        logger.info(f"Found {len(pairs)} pairs to process.")

        # 2. Parallel Process
        all_forecasts = []
        # Use fewer workers to respect 8GB RAM (Stan is memory heavy)
        max_workers = min(4, max(1, cpu_count() - 1))
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_single_task, item_id, district, self.fast_mode) 
                        for item_id, district in pairs]
            
            for i, f in enumerate(futures):
                res = f.result()
                if res:
                    all_forecasts.extend(res)
                if (i+1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{len(pairs)}")

        # 3. Save to DB
        if all_forecasts:
            self._save_to_db(all_forecasts)
            logger.info("Pipeline completed successfully.")
        else:
            logger.warning("No forecasts generated.")

    def _save_to_db(self, forecasts):
        db = SessionLocal()
        try:
            db.query(models.Forecast).delete(synchronize_session=False)
            db.bulk_insert_mappings(inspect(models.Forecast), forecasts)
            db.commit()

            # Cleanup all generated joblib files to save memory and reduce server load
            for f in glob.glob(os.path.join(MODELS_DIR, "*.joblib")):
                try:
                    os.remove(f)
                except Exception as e:
                    logger.warning(f"Could not remove {f}: {e}")
        except Exception as e:
            logger.error(f"Error saving to DB: {e}")
            db.rollback()
        finally:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Set fast_mode=True for "instant" results (skips tuning)
    pipeline = MLPipeline(fast_mode=True)
    pipeline.run()
