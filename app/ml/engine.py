from prophet.forecaster import Prophet
import pandas as pd
import numpy as np

# Forcasting price
def generate_forcast(prices_data):
    if len(prices_data) < 10:
        return [] #need atleast 10 datapoints to see the trend
    
    #Convert DB into a Panda Dataframe
    df = pd.DataFrame(prices_data,columns=['y','ds'])
    
    '''Initialization and Prophet Model training
    Training will be based on 6 months data not yearly data
    So we will be using the daily_seasonality'''
    model = Prophet(daily_seasonality=True,weekly_seasonality=True)
    model.fit(df)
    
    # Create a future timeline for the next 7 days
    future = model.make_future_dataframe(periods=7)
    
    # Predict the prices for those future dates
    forcast = model.predict(future)
    
    '''Extract only the Date (ds) and the Predicted Price (yhat)
    yhat_lower and yhat_upper can be used to show "uncertainty" on
    the graph'''
    results = forcast[['ds','yhat']].tail(7).to_dict('records')
    return results
    
# Anomaly detection 
def detect_anomaly(new_price:float, historical_prices: list):
    """Uses the Z-Score method to detect outliers.
    If a price is more than 3 standard deviations
    away from the mean,it's fake."""
    if not historical_prices:
        return False
    
    # Calculate the average
    mean = np.mean(historical_prices)
    # Calculate the stabdard deviation (How much price vary)
    std_dev = np.std(historical_prices)
    '''This Standard deviation needed to be ckecked further'''
    if std_dev == 0:
        return False 
    # Calculate Z-Score (NewPrice - Mean) / StdDev
    z_Score = abs(new_price - mean) / std_dev
    #Z-Score threshold is needed to be ckecked properly while model training, for now 3 
    return z_Score > 3