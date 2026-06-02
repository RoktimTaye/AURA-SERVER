import pandas as pd
import datetime
from sqlalchemy.orm import Session
from typing import cast
from app.database import SessionLocal
from app import models

def fast_import(csv_path: str):
    db: Session = SessionLocal()
    
    print(f"Reading dataset from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # 1. Handle Kaggle/WFP Specific Format (Remove HXL Tag Row)
    if df.iloc[0]['date'] == '#date':
        print("Detected HXL tag row. Removing...")
        df = df.iloc[1:].copy()
        
    # Convert price to numeric, dropping bad rows immediately
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df = df.dropna(subset=['price', 'date'])
    
    # 2. Ensure GovBot user exists
    gov_bot = db.query(models.User).filter(models.User.email == "agmarknet@gov.in").first()
    if not gov_bot:
        gov_bot = models.User(email="agmarknet@gov.in", role="bot", hashed_password="gov_verified_data")
        db.add(gov_bot)
        db.commit()
        db.refresh(gov_bot)
    
    print("Pre-caching existing database records to maximize speed...")
    
    # Cache Items: {name: id}
    item_cache: dict[str, int] = {str(i.name): cast(int, i.id) for i in db.query(models.Item).all()}
    
    # Cache Locations: {(name, district, state): id}
    loc_cache: dict[tuple[str, str, str], int] = {(str(loc.name), str(loc.district), str(loc.state)): cast(int, loc.id) for loc in db.query(models.Location).all()}
    
    # Cache existing PriceEntries to avoid duplicates
    existing_entries = set()
    print("Loading existing price entries (this may take a moment)...")
    for entry in db.query(models.PriceEntry.item_id, models.PriceEntry.location_id, 
                          models.PriceEntry.timestamp, models.PriceEntry.price)\
                  .filter(models.PriceEntry.user_id == gov_bot.id).all():
        existing_entries.add((entry.item_id, entry.location_id, entry.timestamp, entry.price))

    print(f"Starting import of {len(df)} records from Kaggle Dataset...")
    
    new_entries_count = 0
    batch_size = 1000 # Increased batch size for faster processing of large dataset
    
    for index, row in df.iterrows():
        try:
            # A. Item Lookup/Create
            item_name = str(row['commodity']).strip()
            if item_name not in item_cache:
                new_item = models.Item(name=item_name, unit="kg")
                db.add(new_item)
                db.flush()
                item_cache[item_name] = cast(int, new_item.id)
            item_id = item_cache[item_name]

            # B. Location Lookup/Create
            market = str(row['market']).strip() if pd.notna(row['market']) else "Unknown Market"
            district = str(row['admin2']).strip() if pd.notna(row['admin2']) else "Unknown District"
            state = str(row['admin1']).strip() if pd.notna(row['admin1']) else "Unknown State"
            
            loc_key = (market, district, state)
            
            if loc_key not in loc_cache:
                new_loc = models.Location(name=market, district=district, state=state)
                db.add(new_loc)
                db.flush()
                loc_cache[loc_key] = cast(int, new_loc.id)
            loc_id = loc_cache[loc_key]

            # C. Price Entry & Date Parsing
            try:
                # Kaggle Dataset uses YYYY-MM-DD format
                arrival_date = datetime.datetime.strptime(row['date'], "%Y-%m-%d")
            except ValueError:
                print(f"Row {index}: Invalid date format {row['date']}, skipping.")
                continue
            
            price = float(row['price'])
            
            # Skip if already exists in DB
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
                print(f"💾 Committing batch... ({new_entries_count} new entries saved so far)")
                db.commit()
                
        except Exception as e:
            print(f"Error at row {index}: {e}")
            db.rollback()
            continue

    db.commit()
    print("\n" + "="*50)
    print(f"🎉 IMPORT COMPLETE!")  # noqa: F541
    print(f"Total new historical records added: {new_entries_count}")
    print("="*50)
    db.close()

if __name__ == "__main__":
    # Ensure this points to the correct location of Dataset2.csv
    import os
    # Assuming script is run from the 'Test' folder or root folder
    csv_location = "Dataset2.csv" if os.path.exists("Dataset2.csv") else "../Dataset2.csv"
    
    if os.path.exists(csv_location):
        fast_import(csv_location)
    else:
        print(f"❌ Error: Could not find {csv_location}. Please ensure Dataset2.csv is in the project root.")