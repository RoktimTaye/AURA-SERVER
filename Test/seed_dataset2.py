import pandas as pd
import datetime
from sqlalchemy.orm import Session
import sys
import os
from typing import cast

# Add the app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal, engine, Base
from app import models
from app.crud import pwd_context

def enforce_taxonomy(item_name: str) -> str:
    name = item_name.strip()
    generic_categories = [
        "Lentils", "Rice", "Wheat", "Sugar", "Milk", "Potatoes", 
        "Onions", "Tomatoes", "Tea", "Salt", "Chickpeas"
    ]
    for cat in generic_categories:
        if name.lower() == cat.lower():
            return f"{cat} (General)"
    return name

def seed_dataset2(csv_path: str):
    # Ensure tables exist
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    
    db: Session = SessionLocal()
    # Skip the HXL tag row (the second row) and handle mixed types
    df = pd.read_csv(csv_path, skiprows=[1], low_memory=False)
    
    print("Pre-caching existing data to speed up processing...")
    
    # Cache Items: {name: id}
    item_cache: dict[str, int] = {str(i.name): cast(int, i.id) for i in db.query(models.Item).all()}
    # Cache Locations: {(name, district, state): id}
    loc_cache: dict[tuple[str, str, str], int] = {(str(loc.name), str(loc.district), str(loc.state)): cast(int, loc.id) for loc in db.query(models.Location).all()}
    # Cache Users (Admins): {district: user_id}
    admin_cache: dict[str, int] = {str(u.full_name).replace(" Admin", ""): cast(int, u.id) for u in db.query(models.User).filter(models.User.role == "admin").all()}
    
    existing_entries = set()
    print("Loading existing price entries (this may take a moment)...")
    for entry in db.query(models.PriceEntry.item_id, models.PriceEntry.location_id, 
                        models.PriceEntry.timestamp, models.PriceEntry.price).all():
        existing_entries.add((entry.item_id, entry.location_id, entry.timestamp, entry.price))

    print(f"Starting import of {len(df)} records from {csv_path}...")
    
    new_entries_count = 0
    batch_size = 500
    
    # We will use a single password for all auto-generated admins for presentation purposes
    default_password = pwd_context.hash("admin123")
    
    # Realistic name components to generate 319 unique admin names
    first_names = ["Amit", "Rahul", "Priya", "Sanjay", "Anjali", "Vikram", "Sneha", "Rohan", "Deepika", "Arjun", 
                    "Kavita", "Manish", "Sunita", "Rajesh", "Pooja", "Alok", "Meena", "Vijay", "Neeta", "Kishore"]
    last_names = ["Sharma", "Verma", "Gupta", "Singh", "Mehta", "Patel", "Reddy", "Nair", "Das", "Joshi",
                    "Iyer", "Khan", "Malhotra", "Chaudhary", "Yadav", "Bose", "Kulkarni", "Mishra", "Gill", "Rao"]
    
    admin_name_index = 0

    for index, row in df.iterrows():
        try:
            # 1. Item Lookup/Create
            item_name = enforce_taxonomy(str(row['commodity']))
            if item_name not in item_cache:
                new_item = models.Item(name=item_name, unit=str(row['unit']).lower())
                db.add(new_item)
                db.flush()
                item_cache[item_name] = cast(int, new_item.id)
            item_id = item_cache[item_name]

            # 2. Location Lookup/Create
            market = str(row['market'])
            district = str(row['admin2'])
            state = str(row['admin1'])
            loc_key = (market, district, state)
            
            if loc_key not in loc_cache:
                new_loc = models.Location(name=market, district=district, state=state)
                db.add(new_loc)
                db.flush()
                loc_cache[loc_key] = cast(int, new_loc.id)
            loc_id = loc_cache[loc_key]
            
            # 3. Dynamic Admin Creation per District
            if district not in admin_cache:
                safe_district_name = "".join(e for e in district if e.isalnum()).lower()
                email = f"admin_{safe_district_name}@aura.com"
                
                # Generate a unique real-looking name
                fname = first_names[admin_name_index % len(first_names)]
                lname = last_names[(admin_name_index // len(first_names)) % len(last_names)]
                real_full_name = f"{fname} {lname}"
                admin_name_index += 1
                
                existing_user = db.query(models.User).filter(models.User.email == email).first()
                if not existing_user:
                    new_admin = models.User(
                        email=email, 
                        full_name=real_full_name, # REAL NAME POPULATED HERE
                        role="admin", # SETTING ROLE IN USER TABLE
                        hashed_password=default_password
                    )
                    db.add(new_admin)
                    db.flush()
                    admin_cache[district] = cast(int, new_admin.id)
                    print(f"Created Admin: {real_full_name} for {district}")
                else:
                    admin_cache[district] = cast(int, existing_user.id)
            
            admin_id = admin_cache[district]

            # 4. Price Entry Creation
            try:
                arrival_date = datetime.datetime.strptime(str(row['date']), "%Y-%m-%d")
            except (ValueError, TypeError):
                arrival_date = datetime.datetime.now()
            
            price = float(row['price'])
            
            # Skip if already exists
            if (item_id, loc_id, arrival_date, price) in existing_entries:
                continue

            new_entry = models.PriceEntry(
                item_id=item_id,
                location_id=loc_id,
                user_id=admin_id,
                role="admin",  # SETTING ROLE IN PRICE_ENTRY TABLE
                price=price,
                status="APPROVED",
                timestamp=arrival_date,
                votes=100
            )
            db.add(new_entry)
            new_entries_count += 1
            
            # Add to set to prevent duplicates in the same run
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
    # Ensure this runs exactly like seed_gov_data_fast.py but for Dataset2
    dataset_path = os.path.join(os.path.dirname(__file__), "..", "Data", "Dataset2.csv")
    seed_dataset2(dataset_path)
