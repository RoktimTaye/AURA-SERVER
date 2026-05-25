
import os
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from prophet import Prophet
import matplotlib.pyplot as plt
from sqlalchemy import create_engine
from app.database import SessionLocal, engine
from app import models

# Suppress logs
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def calculate_metrics(actual, predicted):
    actual = np.array(actual)
    predicted = np.array(predicted)
    
    mse = np.mean((actual - predicted)**2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(actual - predicted))
    
    # R-squared calculation
    ss_res = np.sum((actual - predicted)**2)
    ss_tot = np.sum((actual - np.mean(actual))**2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    # MAPE calculation
    mape = np.mean(np.abs((actual - predicted) / actual)) * 100 if np.all(actual != 0) else 0
    
    return {"RMSE": rmse, "MAE": mae, "R2": r2, "MAPE": mape}

def generate_fallback_prediction(df, test_date):
    """
    Mirroring the logic in app/ml/pipeline_1.py (District Level)
    """
    try:
        last_price = float(df['y'].iloc[-1])
        if len(df) >= 2:
            recent_diff = float(df['y'].iloc[-1] - df['y'].iloc[0])
            daily_trend = recent_diff / len(df)
        else:
            daily_trend = 0
            
        last_date = pd.to_datetime(df['ds'].iloc[-1]).tz_localize(None)
        days_diff = (pd.to_datetime(test_date).tz_localize(None) - last_date).days
        
        predicted = last_price + (daily_trend * days_diff)
        return max(0.1, predicted)
    except Exception:
        return None

def backtest_model(item_id, district_name, data_list):
    """
    Performs a sequential backtest for a single item-district pair.
    Uses the last 1 record as the evaluation set.
    """
    df = pd.DataFrame(data_list, columns=['y', 'ds'])
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    df = df.sort_values('ds')

    if len(df) < 2: 
        return None

    train_df = df.iloc[:-1]
    test_df = df.iloc[-1:]
    
    actual = test_df['y'].values[0]
    test_date = test_df['ds'].values[0]

    predicted = None
    method = "None"

    # Attempt Prophet if district-level data is sufficient (10+ points)
    if len(train_df) >= 10:
        try:
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=False,
                yearly_seasonality=False,
                interval_width=0.95
            )
            model.fit(train_df)
            future = pd.DataFrame({'ds': [test_date]})
            forecast = model.predict(future)
            predicted = forecast['yhat'].values[0]
            method = "Prophet"
        except Exception:
            pass

    # Fallback if Prophet fails or data is sparse
    if predicted is None:
        predicted = generate_fallback_prediction(train_df, test_date)
        method = "Fallback"

    if predicted is not None:
        return {
            "actual": actual,
            "predicted": predicted,
            "method": method,
            "residual": actual - predicted
        }
    return None

def run_evaluation():
    logger.info("🧪 Starting District-Level ML Evaluation (Prophet + Fallback)...")
    
    db = SessionLocal()
    try:
        # JOIN with Location to get District names
        query = db.query(
            models.PriceEntry.item_id,
            models.Location.district,
            models.PriceEntry.price,
            models.PriceEntry.timestamp
        ).join(models.Location).filter(models.PriceEntry.status == "APPROVED")
        
        all_data = pd.read_sql(query.statement, engine)
        if all_data.empty:
            logger.warning("No data found for evaluation.")
            return

        # GROUP BY DISTRICT
        groups = all_data.groupby(['item_id', 'district'])
        results = []

        logger.info(f"Analyzing {len(groups)} Item-District pairs...")

        for (item_id, dname), group in groups:
            data_list = group[['price', 'timestamp']].values.tolist()
            res = backtest_model(item_id, dname, data_list)
            if res:
                results.append(res)

        if not results:
            logger.warning("No successful evaluations performed.")
            return

        results_df = pd.DataFrame(results)
        
        # Calculate overall metrics
        metrics = calculate_metrics(results_df['actual'], results_df['predicted'])
        
        print("\n" + "="*50)
        print("📊 AGGREGATED EVALUATION METRICS (District System)")
        print("="*50)
        print(f"Average RMSE: {metrics['RMSE']:.4f}")
        print(f"Average MAE:  {metrics['MAE']:.4f}")
        print(f"Average MAPE: {metrics['MAPE']:.2f}%")
        print(f"Method Usage: \n{results_df['method'].value_counts()}")
        print("="*50)

        # Residual Analysis
        plt.figure(figsize=(10, 6))
        plt.hist(results_df['residual'], bins=30, color='purple', alpha=0.7, edgecolor='black')
        plt.axvline(0, color='red', linestyle='--')
        plt.title("District Residual Analysis (Prophet + Fallback)")
        plt.xlabel("Price Deviation")
        plt.ylabel("Frequency")
        plt.grid(axis='y', alpha=0.3)
        plt.savefig("Test/evaluation_residuals_district.png")
        print("📈 Residual histogram saved to 'Test/evaluation_residuals_district.png'")

    finally:
        db.close()

if __name__ == "__main__":
    run_evaluation()
