import pandas as pd
from app.database import SessionLocal
from app import models

def verify_data():
    db = SessionLocal()
    df = pd.read_csv("Government-Dataset.csv")
    
    csv_total = len(df)
    csv_unique_items = df['Commodity'].nunique()
    csv_unique_locations = df.groupby(['Market', 'District', 'State']).ngroups

    # Database counts
    db_items = db.query(models.Item).count()
    db_locations = db.query(models.Location).count()
    
    # Count PriceEntries created by the GovBot
    gov_bot = db.query(models.User).filter(models.User.email == "agmarknet@gov.in").first()
    if gov_bot:
        db_price_entries = db.query(models.PriceEntry).filter(models.PriceEntry.user_id == gov_bot.id).count()
    else:
        db_price_entries = 0

    print("--- Verification Results ---")
    print(f"CSV Total Records: {csv_total}")
    print(f"DB Price Entries (GovBot): {db_price_entries}")
    
    if csv_total == db_price_entries:
        print("✅ SUCCESS: All price records uploaded correctly.")
    else:
        print(f"⚠️ MISMATCH: {csv_total - db_price_entries} records missing.")

    print("\n--- Structural Counts ---")
    print(f"Items in CSV: {csv_unique_items} | Items in DB: {db_items}")
    print(f"Locations in CSV: {csv_unique_locations} | Locations in DB: {db_locations}")
    
    db.close()

if __name__ == "__main__":
    verify_data()
