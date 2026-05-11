import joblib  # noqa: F401
import pandas as pd
from prophet import Prophet
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..import models

def run_ml_pipeline():
    