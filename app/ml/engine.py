import numpy as np
# Anomaly detection 
def detect_anomaly(new_price:float, historical_prices: list):
    """Uses the Z-Score method to detect outliers.
    If a price is more than 3 standard deviations
    away from the mean,it's fake."""
    if not historical_prices or len(historical_prices) < 2:
        return False
    
    # Calculate the average
    mean = np.mean(historical_prices)
    # Calculate the stabdard deviation (How much price vary)
    std_dev = np.std(historical_prices)
    '''This Standard deviation needed to be ckecked further'''
    if std_dev == 0:
        return abs(new_price - mean) > (mean * 0.5)
    # Calculate Z-Score (NewPrice - Mean) / StdDev
    z_Score = abs(new_price - mean) / std_dev
    #Z-Score threshold is needed to be ckecked properly while model training, for now 3 
    return z_Score > 3