import os
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, UTC
from prophet import Prophet
from sqlalchemy import inspect
from app.database import SessionLocal, engine
from app import models
from app.ml.aura_ml_pipeline import hyperparameter_tuning, generate_fallback_forecast, MIN_DATA_POINTS

# Suppress Prophet/CmdStanPy logs
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Output directory for plots
PLOTS_DIR = os.path.join("Test", "evaluation_plots")
os.makedirs(PLOTS_DIR, exist_ok=True)

def calculate_metrics(actual, predicted):
    actual = np.array(actual)
    predicted = np.array(predicted)
    
    # Avoid division by zero for MAPE
    mask = actual != 0
    if not np.any(mask):
        mape = np.nan
    else:
        mape = np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100
        
    mse = np.mean((actual - predicted)**2)
    rmse = np.sqrt(mse)
    mae = np.mean(np.abs(actual - predicted))
    
    # R-squared
    ss_res = np.sum((actual - predicted)**2)
    ss_tot = np.sum((actual - np.mean(actual))**2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    return {"RMSE": rmse, "MAE": mae, "MAPE": mape, "R2": r2}

def evaluate_pipeline_on_pair(item_id, district_name, data_list):
    """
    Evaluates the aura_ml_pipeline logic on a single item-district pair.
    Withholds the last 7 days for testing.
    """
    df = pd.DataFrame(data_list, columns=['y', 'ds'])
    df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
    df = df.sort_values('ds')
    
    # Mirror outlier removal from pipeline
    if len(df) > 5:
        y_mean = df['y'].mean()
        y_std = df['y'].std()
        if y_std > 0:
            df = df[((df['y'] - y_mean) / y_std).abs() < 3]

    # The pipeline requires at least MIN_DATA_POINTS (20) to attempt Prophet.
    # For evaluation, we also need 7 points for the test set.
    if len(df) < MIN_DATA_POINTS + 7:
        # If we have enough for fallback, we could evaluate fallback, 
        # but let's stick to pairs that have at least some decent history.
        if len(df) < 10: # Absolute minimum to evaluate anything
            return None
        
        # Split for fallback evaluation
        history_df = df.iloc[:-7]
        test_df = df.iloc[-7:]
        if len(test_df) == 0: return None
        
        actuals = test_df['y'].values
        fallback_results = generate_fallback_forecast(history_df, item_id, district_name)
        if fallback_results:
            predictions = np.array([res['predicted_price'] for res in fallback_results])[:len(actuals)]
            method = "Fallback"
        else:
            return None
    else:
        # Sufficient data for Prophet attempt
        history_df = df.iloc[:-7]
        test_df = df.iloc[-7:]
        actuals = test_df['y'].values
        test_dates = test_df['ds'].values
        
        try:
            # Replicate the tuning logic on history_df
            # Note: history_df.iloc[:-7] and history_df.iloc[-7:] are used for tuning within history_df
            train_tuning = history_df.iloc[:-7]
            test_tuning = history_df.iloc[-7:]
            best_params = hyperparameter_tuning(train_tuning, test_tuning)
            
            model = Prophet(yearly_seasonality=True, daily_seasonality=False, weekly_seasonality=False, **best_params)
            model.fit(history_df)
            
            future = pd.DataFrame({'ds': test_dates})
            forecast = model.predict(future)
            predictions = forecast['yhat'].values
            method = "Prophet (Tuned)"
        except Exception as e:
            # Replicate fallback on failure
            fallback_results = generate_fallback_forecast(history_df, item_id, district_name)
            if fallback_results:
                predictions = np.array([res['predicted_price'] for res in fallback_results])[:len(actuals)]
                method = "Fallback (Prophet Failed)"
            else:
                return None

    # Baseline: Persistence (last known value)
    last_val = history_df['y'].iloc[-1]
    baseline_preds = np.full(len(actuals), last_val)
    
    metrics = calculate_metrics(actuals, predictions)
    baseline_metrics = calculate_metrics(actuals, baseline_preds)
    
    return {
        "item_id": item_id,
        "district": district_name,
        "metrics": metrics,
        "baseline_metrics": baseline_metrics,
        "method": method,
        "actuals": actuals,
        "predictions": predictions,
        "test_dates": test_df['ds'].values
    }

def run_evaluation():
    logger.info("🚀 Starting Senior-Level ML Evaluation of 'aura_ml_pipeline.py'...")
    
    db = SessionLocal()
    try:
        query = db.query(
            models.PriceEntry.item_id,
            models.Location.district,
            models.PriceEntry.price,
            models.PriceEntry.timestamp
        ).join(models.Location).filter(models.PriceEntry.status == "APPROVED")
        
        all_data = pd.read_sql(query.statement, engine)
        if all_data.empty:
            logger.error("❌ No data found in database. Evaluation cannot proceed.")
            return

        groups = all_data.groupby(['item_id', 'district'])
        results = []

        logger.info(f"Analyzing {len(groups)} Item-District pairs for 7-day holdout...")

        for (item_id, dname), group in groups:
            data_list = group[['price', 'timestamp']].values.tolist()
            res = evaluate_pipeline_on_pair(item_id, dname, data_list)
            if res:
                results.append(res)

        if not results:
            logger.warning("⚠️ No pairs met the minimum data requirements for evaluation.")
            return

        # --- AGGREGATION ---
        eval_df = pd.DataFrame([
            {
                "item_id": r['item_id'],
                "district": r['district'],
                "method": r['method'],
                "RMSE": r['metrics']['RMSE'],
                "MAE": r['metrics']['MAE'],
                "MAPE": r['metrics']['MAPE'],
                "R2": r['metrics']['R2'],
                "B_RMSE": r['baseline_metrics']['RMSE'],
                "B_MAPE": r['baseline_metrics']['MAPE']
            } for r in results
        ])

        # Overall Summary
        print("\n" + "="*60)
        print("📊 AURA ML PIPELINE EVALUATION REPORT")
        print("="*60)
        print(f"Total Pairs Evaluated: {len(eval_df)}")
        print(f"Method Distribution:\n{eval_df['method'].value_counts()}")
        print("-" * 60)
        
        print(f"Mean RMSE:  {eval_df['RMSE'].mean():.4f} (Baseline: {eval_df['B_RMSE'].mean():.4f})")
        print(f"Mean MAE:   {eval_df['MAE'].mean():.4f}")
        print(f"Mean MAPE:  {eval_df['MAPE'].mean():.2f}% (Baseline: {eval_df['B_MAPE'].mean():.2f}%)")
        print(f"Mean R2:    {eval_df['R2'].mean():.4f}")
        
        # Improvement over baseline
        mape_imp = (eval_df['B_MAPE'].mean() - eval_df['MAPE'].mean()) / eval_df['B_MAPE'].mean() * 100
        print(f"Improvement over Persistence: {mape_imp:.2f}% (in terms of MAPE)")
        print("="*60)

        # --- VISUALIZATION ---
        
        # 1. Residual Distribution
        all_residuals = []
        for r in results:
            all_residuals.extend(r['actuals'] - r['predictions'])
        
        plt.figure(figsize=(10, 6))
        plt.hist(all_residuals, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
        plt.axvline(0, color='red', linestyle='--', label='Zero Error')
        plt.title("Overall Residual Distribution (Predicted - Actual)")
        plt.xlabel("Price Difference")
        plt.ylabel("Frequency")
        plt.legend()
        plt.grid(alpha=0.3)
        plt.savefig(os.path.join(PLOTS_DIR, "overall_residuals.png"))
        
        # 2. Performance by Method
        plt.figure(figsize=(10, 6))
        eval_df.groupby('method')['MAPE'].mean().plot(kind='bar', color=['green', 'orange', 'red'])
        plt.title("Average MAPE by Prediction Method")
        plt.ylabel("MAPE (%)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(PLOTS_DIR, "method_performance.png"))

        # 3. Sample Plot (Top performing pair)
        best_pair = eval_df.loc[eval_df['MAPE'].idxmin()]
        best_res = next(r for r in results if r['item_id'] == best_pair['item_id'] and r['district'] == best_pair['district'])
        
        plt.figure(figsize=(12, 6))
        plt.plot(best_res['test_dates'], best_res['actuals'], 'o-', label='Actual', color='black')
        plt.plot(best_res['test_dates'], best_res['predictions'], 's--', label='Prophet Predicted', color='blue')
        plt.title(f"Sample Forecast: Item {best_res['item_id']} in {best_res['district']}")
        plt.legend()
        plt.grid(alpha=0.3)
        plt.savefig(os.path.join(PLOTS_DIR, "sample_forecast.png"))

        logger.info(f"✅ Evaluation complete. Plots saved to '{PLOTS_DIR}'")

    finally:
        db.close()

if __name__ == "__main__":
    run_evaluation()
