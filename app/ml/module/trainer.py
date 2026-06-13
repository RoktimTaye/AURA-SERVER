import logging
import itertools
import pandas as pd
from prophet import Prophet
from .evaluator import Evaluator

logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self, fast_mode=False):
        self.fast_mode = fast_mode
        self.evaluator = Evaluator()

    def tune_and_train(self, df):
        """
        Hyperparameter tuning followed by final training.
        """
        if len(df) < 15 or self.fast_mode:
            # Default parameters for fast mode or small datasets
            best_params = {'changepoint_prior_scale': 0.05, 'seasonality_prior_scale': 10.0}
        else:
            best_params = self._hyperparameter_tuning(df)
        
        # Final model training
        model = self._create_model(best_params)
        model.fit(df)
        return model, best_params

    def _create_model(self, params):
        return Prophet(
            growth='logistic',
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False, # Set to False for monthly/daily hybrid data usually
            **params
        )

    def _hyperparameter_tuning(self, df):
        # Sequential split
        train_df = df.iloc[:-7]
        test_df = df.iloc[-7:]
        
        param_grid = {
            'changepoint_prior_scale': [0.01, 0.1],
            'seasonality_prior_scale': [1.0, 10.0]
        }
        all_params = [dict(zip(param_grid.keys(), v)) for v in itertools.product(*param_grid.values())]
        
        best_rmse = float('inf')
        best_params = {'changepoint_prior_scale': 0.05, 'seasonality_prior_scale': 10.0}
        
        for params in all_params:
            try:
                m = self._create_model(params).fit(train_df)
                future = pd.DataFrame({'ds': test_df['ds'], 'cap': test_df['cap'], 'floor': test_df['floor']})
                forecast = m.predict(future)
                
                rmse = self.evaluator.calculate_rmse(test_df['y'], forecast['yhat'])
                if rmse < best_rmse:
                    best_rmse = rmse
                    best_params = params
            except Exception:
                continue
        return best_params
