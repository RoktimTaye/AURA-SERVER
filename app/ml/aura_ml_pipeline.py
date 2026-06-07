import os
import logging
import joblib
import itertools
import pandas as pd
import numpy as np
import glob
from typing import Any
from datetime import datetime,UTC
from prophet import Prophet
from sqlalchemy import inspect
from ..database import SessionLocal, engine
from .. import models

logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

logging.basicConfig(level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MIN_DATA_POINTS = 20
MODELS_DIR = os.path.join("app","ml","models_district_tuned")
os.makedirs(MODELS_DIR,exist_ok=True)

def hyperparameter_tuning(train_df,test_df):
    param_grid = {
        'changepoint_prior_scale': [0.01, 0.1],
        'seasonality_prior_scale': [1.0,10.0]
    }
    all_params = [dict(zip(param_grid.keys(),V)) for V in itertools.product(*param_grid.values())]
    
    best_rmse = float('inf')
    best_params = {'changepoint_prior_scale': 0.05, 'seasonality_prior_scale':10.0}
    
    for params in all_params:
        try:
            model = Prophet(yearly_seasonality=True,daily_seasonality=False,weekly_seasonality=False, **params) # type: ignore
            model.fit(train_df)
            future = pd.DataFrame({'ds': test_df['ds']})
            forecast = model.predict(future)
            rmse = np.sqrt(np.mean((test_df['y'].values -forecast['yhat'].values)**2))
            if rmse < best_rmse:
                best_rmse = rmse
                best_params = params
        except Exception:
            continue
    return best_params

def generate_fallback_forecast(df,item_id,district_name):
    try:
        last_price = float(df['y'].iloc[-1])
        if len(df) >= 2:
            recent_diff = float(df['y'].iloc[-1] - df['y'].iloc[0])
            daily_trend = recent_diff / len(df)
        else:
            daily_trend = 0
        last_date = pd.to_datetime(df['ds'].iloc[-1]).tz_localize(None)
        results = []
        
        for i in range(1,8):
            target_date = (last_date + pd.Timedelta(days=i)).to_pydatetime()
            predicted = last_price + (daily_trend * i)
            predicted = max(0.1,predicted)
            
            results.append({
                "item_id":item_id,
                "district":district_name,
                "location_id":None,
                "target_date":target_date,
                "predicted_price": round(float(predicted), 2),
                "yhat_lower": round(float(predicted * 0.9), 2),
                "yhat_upper": round(float(predicted * 1.1), 2),
                "trend": "UP" if daily_trend > 0.01 else "DOWN" if daily_trend < -0.01 else "STABLE",
                "created_at": datetime.now(UTC).replace(tzinfo=None)
            })
        return results
    except Exception as e:
        logger.error(f"Fallback failed for {item_id} in {district_name}: {e}")
        return None

def train_single_model(item_id,district_name,data_list):
    df = pd.DataFrame(data_list,columns=['y','ds'])
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    df = df.sort_values('ds')
    
    if len(df) > 5:
        y_mean = df['y'].mean()
        y_std = df['y'].std()
        if y_std > 0:
            df = df[((df['y'] - y_mean) / y_std).abs() < 3]
    
    try:
        if len(df) >= MIN_DATA_POINTS:
            train_df = df.iloc[:-7]
            test_df = df.iloc[-7:]
            best_params = hyperparameter_tuning(train_df,test_df)
            model = Prophet(yearly_seasonality=True,daily_seasonality=False,weekly_seasonality=False, **best_params)
            model.fit(df)
            safe_district = str(district_name).replace(" ","_").replace("/","_")
            model_path = os.path.join(MODELS_DIR,f"brain_{item_id}_{safe_district}.joblib")
            joblib.dump(model,model_path)
            
            future = model.make_future_dataframe(periods=7)
            forecast = model.predict(future).tail(7)
            results = []
            for _, row in forecast.iterrows():
                results.append({
                    "item_id": item_id,
                    "district":district_name,
                    "location_id":None,
                    "target_date": row['ds'].to_pydatetime(),
                    "predicted_price": round(float(row['yhat']),2),
                    "yhat_lower": round(float(row['yhat_lower']),2),
                    "yhat_upper": round(float(row['yhat_upper']),2),
                    "trend": "STABLE",
                    "created_at": datetime.now(UTC).replace(tzinfo=None)
                })
            return results
    except Exception as e:
        logger.warning(f"Prophet failed for {item_id} in {district_name}: {e}")
    return generate_fallback_forecast(df,item_id,district_name)

def run_ml_pipeline():
    logger.info("Starting Tuned District-Level ML pipeline")
    
    db = SessionLocal()
    try:
        logger.info("Fetching historical price data by District")
        query = db.query(
            models.PriceEntry.item_id,
            models.Location.district,
            models.PriceEntry.price,
            models.PriceEntry.timestamp
        ).join(models.Location).filter(models.PriceEntry.status== "APPROVED")
        
        all_data = pd.read_sql(query.statement,engine)
        if all_data.empty:
            logger.warning("No data found")
            return
        groups = all_data.groupby(['item_id','district'])
        tasks = []
        for key,group in groups:
            if isinstance(key,tuple) and len(key) == 2:
                item_id: Any = key[0]
                district_name: Any = key[1]
                data_list = group[['price','timestamp']].values.tolist()
                tasks.append((int(item_id), district_name, data_list))
        logger.info(f"Found {len(tasks)} Item-District pairs to forecast")
        
        all_forecasts = []
        for tid, dname, data in tasks:
            result = train_single_model(tid,dname,data)
            if result:
                all_forecasts.extend(result)
        if all_forecasts:
            logger.info(f"Updating database with {len(all_forecasts)} optimized forecasts")
            try:
                db.query(models.Forecast).delete(synchronize_session=False)
                db.bulk_insert_mappings(inspect(models.Forecast),all_forecasts)
                db.commit()

                # Cleanup joblib files to save memory and reduce server load
                for f in glob.glob(os.path.join(MODELS_DIR, "*.joblib")):
                    try:
                        os.remove(f)
                    except Exception as e:
                        pass

                logger.info("Production Pipeline Complete! Forecast are now optimized")
            except Exception as e:
                db.rollback()
                logger.error(f"DB update failed {e}")
        else:
            logger.warning("No forecast generated")
    except Exception as  e:
        logger.error(f"Pipeline Error {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_ml_pipeline()