import joblib  # noqa: F401
import pandas as pd  # noqa: F401
from prophet import Prophet  # noqa: F401
from sqlalchemy.orm import Session  # noqa: F401
from ..database import SessionLocal
from ..import models  # noqa: F401

def run_ml_pipeline():
    db = SessionLocal()  # noqa: F841
    items = db.query(models.Item).all()
    locations = db.query(models.Location).all()
    
    #Fetching hostorical data from the dataset (Item + Location)
    for item in items:
        for loc in locations:
            data = db.query(models.PriceEntry.price,  # noqa: F841
                            models.PriceEntry.item_id == item.id,
                            models.PriceEntry.location_id == loc.id,
                            models.PriceEntry.status == "APPROVED").all()
            
            if len(data) < 10 : continue  # noqa: E701
            
            #Training Prophet Model
            df = pd.DataFrame(data,columns=['y','ds'])  # noqa: F841
            model = Prophet(daily_seasonality=True,weekly_seasonality=True)  # noqa: F841
            model.fit(df)
            
            #Save the Brain
            joblib.dump(model,f"app/ml/models/brain_{item.id}_{loc.id}.joblib")
            
            # Generate and save 7-days Forecast
            future = model.make_future_dataframe(periods=7)  # noqa: F841
            forecast = model.predict(future).tail(7)  # noqa: F841
            
            for _, row in forecast.iterrows():
                new_forecast = models.Forecast(  # noqa: F841
                item_id = item.id,  # noqa: F841
                location_id = loc.id,  # noqa: F841
                target_date = row['ds'],
                predicted_price = row['yhat'],
                yhat_lower = row['yhat_lower'],
                yhat_upper = row['yhat_upper'])
                db.add(new_forecast)
                db.commit()
                db.close()