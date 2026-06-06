import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

class Preprocessor:
    def __init__(self, z_threshold=3.0, use_log_transform=True):
        self.z_threshold = z_threshold
        self.use_log_transform = use_log_transform

    def process(self, df):
        """
        Main preprocessing pipeline:
        1. Clean dates and types.
        2. Remove outliers.
        3. Feature engineering (log transform).
        """
        if df.empty:
            return df

        df = df.copy()
        
        # 1. Cleaning
        df['ds'] = pd.to_datetime(df['ds']).dt.tz_localize(None)
        df['y'] = pd.to_numeric(df['y'], errors='coerce')
        df = df.dropna(subset=['ds', 'y'])
        df = df.sort_values('ds')

        # 2. Outlier Removal (Z-Score)
        if len(df) > 5:
            m, s = df['y'].mean(), df['y'].std()
            if s > 0:
                df = df[((df['y'] - m) / s).abs() <= self.z_threshold]

        # 3. Log Transformation
        if self.use_log_transform:
            df['y'] = np.log1p(df['y'])

        return df

    def inverse_transform(self, series):
        """Inverts the log transformation."""
        if self.use_log_transform:
            return np.expm1(series)
        return series
