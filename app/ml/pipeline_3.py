import os
import logging
import itertools
import pandas as pd
import numpy as np
from datetime import datetime
from prophet import Prophet
import warnings

# Suppress logs for cleaner output
logging.getLogger('prophet').setLevel(logging.ERROR)
logging.getLogger('cmdstanpy').setLevel(logging.ERROR)
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
DATA_PATH = 'Dataset2.csv'
MODELS_DIR = os.path.join("app", "ml", "models_tuned")
os.makedirs(MODELS_DIR, exist_ok=True)

# We will limit to 5 groups for the demonstration so it doesn't take hours to run. 
# Set to None to process the entire dataset.
MAX_GROUPS_TO_PROCESS = 5 

def load_and_preprocess_data(filepath):
    """
    Step 1: Data Preprocessing & Feature Engineering
    """
    logger.info("📥 Loading and preprocessing data...")
    # Load dataset
    df = pd.read_csv(filepath)
    
    # WFP Kaggle datasets often have an 'HXL' tag row right after the header. Remove it.
    if df.iloc[0]['date'] == '#date':
        df = df.iloc[1:].copy()
        
    # Apply Schema Mapping
    column_mapping = {
        'date': 'ds',            # Prophet requirement
        'price': 'y',            # Prophet requirement
        'admin2': 'district',
        'admin1': 'state',
        'commodity': 'item_name'
    }
    df = df.rename(columns=column_mapping)
    
    # Feature Engineering: Date conversion & numeric prices
    df['ds'] = pd.to_datetime(df['ds'])
    df['y'] = pd.to_numeric(df['y'], errors='coerce')
    
    # Handle Missing Values
    df = df.dropna(subset=['ds', 'y'])
    
    # Outlier Removal (Z-Score by Item)
    df['price_zscore'] = df.groupby('item_name')['y'].transform(
        lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0
    )
    df = df[df['price_zscore'].abs() < 3].drop(columns=['price_zscore'])
    
    # Vocabulary Generation (Internal IDs)
    unique_items = sorted(df['item_name'].unique())
    vocabulary = {name: idx + 1 for idx, name in enumerate(unique_items)}
    df['item_id'] = df['item_name'].map(vocabulary)
    
    logger.info(f"✅ Preprocessing complete. Final shape: {df.shape}")
    return df, vocabulary

def hyperparameter_tuning(train_df, test_df):
    """
    Step 3, 4, 5, 6: Hyperparameter Tuning, Eval, and Selection
    Tests multiple parameter combinations and selects the best based on RMSE.
    """
    # Define Parameter Grid
    param_grid = {
        'changepoint_prior_scale': [0.01, 0.1],
        'seasonality_prior_scale': [1.0, 10.0]
    }
    
    # Generate all combinations
    all_params = [dict(zip(param_grid.keys(), v)) for v in itertools.product(*param_grid.values())]
    
    best_rmse = float('inf')
    best_params = None
    best_metrics = {}
    
    for params in all_params:
        try:
            # 1. Train Model with specific params
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=False,
                yearly_seasonality=True,
                **params
            ) # type: ignore
            model.fit(train_df)
            
            # 2. Predict on Test set dates
            future = pd.DataFrame({'ds': test_df['ds']})
            forecast = model.predict(future)
            
            # 3. Model Evaluation using numpy
            actual = test_df['y'].values
            predicted = forecast['yhat'].values
            
            rmse = np.sqrt(np.mean((actual - predicted)**2))
            mae = np.mean(np.abs(actual - predicted))
            
            # 4. Model Selection Logic
            if rmse < best_rmse:
                best_rmse = rmse
                best_params = params
                best_metrics = {'RMSE': rmse, 'MAE': mae}
                
        except Exception as e:
            continue
            
    return best_params, best_metrics

def process_single_group(item_id, district, group_df):
    """
    Orchestrates splitting, tuning, and final forecasting for one specific group.
    """
    group_df = group_df.sort_values('ds')
    
    # We need enough data to split and train
    if len(group_df) < 20:
        return None
        
    # Step 2: Data Splitting (Sequential Hold-Out)
    # Kaggle data is monthly. We will hold out the last 6 records (6 months) for testing.
    train_df = group_df.iloc[:-6]
    test_df = group_df.iloc[-6:]
    
    # Run Hyperparameter Tuning
    best_params, best_metrics = hyperparameter_tuning(train_df, test_df)
    
    if not best_params:
        return None # All tuning attempts failed
        
    # Step 7: Final Model Training (On ALL data using BEST params)
    final_model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=False,
        yearly_seasonality=True,
        **best_params
    ) # type: ignore
    final_model.fit(group_df) # Train on full historical data
    
    # Step 8: Final Model Testing (Predicting upcoming 7 days)
    # freq='D' ensures we predict the next 7 specific days, even if training data was monthly
    future = final_model.make_future_dataframe(periods=7, freq='D')
    final_forecast = final_model.predict(future).tail(7)
    
    return {
        'item_id': item_id,
        'district': district,
        'best_params': best_params,
        'metrics': best_metrics,
        '7_day_forecast': final_forecast[['ds', 'yhat']].to_dict('records')
    }

def run_pipeline():
    logger.info("🚀 Starting Advanced ML Pipeline (Tuning & Evaluation)...")
    
    if not os.path.exists(DATA_PATH):
        logger.error(f"Dataset not found at {DATA_PATH}. Please verify the path.")
        return
        
    df, vocabulary = load_and_preprocess_data(DATA_PATH)
    
    groups = df.groupby(['item_id', 'district'])
    total_groups = len(groups)
    
    logger.info(f"Found {total_groups} unique Item-District groups.")
    
    processed_count = 0
    success_count = 0
    
    print("\n" + "="*60)
    print(f"🔬 RUNNING MODEL TUNING & SELECTION (Max: {MAX_GROUPS_TO_PROCESS})")
    print("="*60)
    
    for (item_id, district), group_df in groups:
        if MAX_GROUPS_TO_PROCESS and processed_count >= MAX_GROUPS_TO_PROCESS:
            break
            
        processed_count += 1
        
        # Execute the full ML lifecycle for this group
        result = process_single_group(item_id, district, group_df)
        
        if result:
            success_count += 1
            print(f"✅ Success: Item {item_id} in {district}")
            print(f"   -> Best Params: {result['best_params']}")
            print(f"   -> Evaluation:  RMSE={result['metrics']['RMSE']:.2f}, MAE={result['metrics']['MAE']:.2f}")
            print(f"   -> Forecast Day 1: {result['7_day_forecast'][0]['yhat']:.2f} INR")
        else:
            print(f"⚠️ Skipped: Item {item_id} in {district} (Insufficient Data / Tuning Failed)")

    print("\n" + "="*60)
    print("📊 PIPELINE EXECUTION SUMMARY")
    print("="*60)
    print(f"Groups Processed: {processed_count}")
    print(f"Models Successfully Tuned & Trained: {success_count}")
    print("="*60)

if __name__ == "__main__":
    run_pipeline()
