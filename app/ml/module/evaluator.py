import numpy as np

class Evaluator:
    @staticmethod
    def calculate_rmse(actual, predicted):
        """Root Mean Squared Error."""
        return np.sqrt(np.mean((actual - predicted)**2))

    @staticmethod
    def calculate_mae(actual, predicted):
        """Mean Absolute Error."""
        return np.mean(np.abs(actual - predicted))

    @staticmethod
    def calculate_mape(actual, predicted):
        """Mean Absolute Percentage Error."""
        return np.mean(np.abs((actual - predicted) / actual)) * 100
