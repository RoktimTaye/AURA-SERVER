import pandas as pd
import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models

def import_gov_data(csv_path: str):
    db: Session = SessionLocal()
    df = pd.read_csv(csv_path)

    # 1. Create a "GovBot" user if it doesn't exist
    gov_bot = db.query(models.User).filter(models.User.email == "agmarknet@gov.in").first()
    if not gov_bot:
        gov_bot = models.User(email="agmarknet@gov.in", role="bot", hashed_password="gov_verified_data")
        db.add(gov_bot)
        db.commit()
        db.refresh(gov_bot)

    print(f"Importing {len(df)} records from {csv_path}...")

    for index, row in df.iterrows():
        # A. Get or Create Item
        item = db.query(models.Item).filter(models.Item.name == row['Commodity']).first()
        if not item:
            item = models.Item(name=row['Commodity'], unit="kg") # Defaulting to kg
            db.add(item)
            db.commit()
            db.refresh(item)

        # B. Get or Create Location (with new District/State fields)
        loc = db.query(models.Location).filter(
            models.Location.name == row['Market'],
            models.Location.district == row['District']
        ).first()

        if not loc:
            loc = models.Location(
                name=row['Market'],
                district=row['District'],
                state=row['State']
            )
            db.add(loc)
            db.commit()
            db.refresh(loc)

        # C. Create Price Entry
        # Format date: 21/04/2026 -> datetime object
        try:
            arrival_date = datetime.datetime.strptime(row['Arrival_Date'], "%d/%m/%Y")
        except Exception:
            arrival_date = datetime.datetime.now()

        new_entry = models.PriceEntry(
            item_id=item.id,
            location_id=loc.id,
            user_id=gov_bot.id,
            price=float(row['Modal_x0020_Price']),
            status="APPROVED",
            timestamp=arrival_date,
            votes=100 # High trust for Govt data
        )
        db.add(new_entry)

        if index % 100 == 0:  # ty:ignore[unsupported-operator]
            print(f"Processed {index} rows...")
            db.commit()

    db.commit()
    print("Import Complete!")
    db.close()

if __name__ == "__main__":
    import_gov_data("Government-Dataset.csv")
