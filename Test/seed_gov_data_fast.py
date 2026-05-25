import pandas as pd
import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models
def fast_import(csv_path: str):
    db: Session = SessionLocal()
    df = pd.read_csv(csv_path)
    
    # 1. Ensure GovBot user exists
    gov_bot = db.query(models.User).filter(models.User.email == "agmarknet@gov.in").first()
    if not gov_bot:
        gov_bot = models.User(email="agmarknet@gov.in", role="bot", hashed_password="gov_verified_data")
        db.add(gov_bot)
        db.commit()
        db.refresh(gov_bot)
    
    print("Pre-caching existing data to speed up processing...")
    # Cache Items: {name: id}
    item_cache = {i.name: i.id for i in db.query(models.Item).all()}
    # Cache Locations: {(name, district, state): id}
    loc_cache = {(l.name, l.district, l.state): l.id for l in db.query(models.Location).all()}
    # Cache existing PriceEntries to avoid duplicates: {(item_id, loc_id, timestamp, price)}
    # We only cache the GovBot's entries to save memory
    existing_entries = set()
    print("Loading existing price entries (this may take a moment)...")
    for entry in db.query(models.PriceEntry.item_id, models.PriceEntry.location_id, 
                          models.PriceEntry.timestamp, models.PriceEntry.price)\
                  .filter(models.PriceEntry.user_id == gov_bot.id).all():
        existing_entries.add((entry.item_id, entry.location_id, entry.timestamp, entry.price))

    print(f"Starting import of {len(df)} records...")
    
    new_entries_count = 0
    batch_size = 500
    
    for index, row in df.iterrows():
        try:
            # A. Item Lookup/Create
            item_name = str(row['Commodity'])
            if item_name not in item_cache:
                new_item = models.Item(name=item_name, unit="kg")
                db.add(new_item)
                db.flush()
                item_cache[item_name] = new_item.id
            item_id = item_cache[item_name]

            # B. Location Lookup/Create
            market = str(row['Market'])
            district = str(row['District'])
            state = str(row['State'])
            loc_key = (market, district, state)
            
            if loc_key not in loc_cache:
                new_loc = models.Location(name=market, district=district, state=state)
                db.add(new_loc)
                db.flush()
                loc_cache[loc_key] = new_loc.id
            loc_id = loc_cache[loc_key]

            # C. Price Entry
            try:
                arrival_date = datetime.datetime.strptime(row['Arrival_Date'], "%d/%m/%Y")
            except:
                arrival_date = datetime.datetime.now()
            
            price = float(row['Modal_x0020_Price'])
            
            # Skip if already exists
            if (item_id, loc_id, arrival_date, price) in existing_entries:
                continue

            new_entry = models.PriceEntry(
                item_id=item_id,
                location_id=loc_id,
                user_id=gov_bot.id,
                price=price,
                status="APPROVED",
                timestamp=arrival_date,
                votes=100
            )
            db.add(new_entry)
            new_entries_count += 1
            
            # Add to set so we don't duplicate within the same run
            existing_entries.add((item_id, loc_id, arrival_date, price))

            if new_entries_count % batch_size == 0 and new_entries_count > 0:
                print(f"Committing batch... (Row {index} reached, {new_entries_count} new entries saved)")
                db.commit()
                
        except Exception as e:
            print(f"Error at row {index}: {e}")
            db.rollback()
            continue

    db.commit()
    print(f"Import Complete! Total new records added: {new_entries_count}")
    db.close()

if __name__ == "__main__":
    fast_import("Government-Dataset.csv")
