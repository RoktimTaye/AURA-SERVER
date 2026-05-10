import math
import random
import datetime
import sys
import os
from sqlalchemy.orm import Session

# 1. FIX: Add current directory to sys.path so 'app' is recognized correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.database import SessionLocal, engine, Base
    from app import models
except ImportError:
    print("Error: Could find 'app' module. Please ensure this script is in the Project Root.")
    sys.exit(1)

# 1. Create the tables in the Cloud (Neon)
print("Connecting to database and creating tables...")
Base.metadata.create_all(bind=engine)

def seed_data():
    db: Session = SessionLocal()
    
    # --- A. INITIALIZE MASTER TABLES ---
    print("Seeding Items and Locations...")
    
    # 1. Create Areas (Locations)
    areas = ["Jorhat", "Guwahati", "Silchar", "Tezpur", "Nagaon", "Dibrugarh", "Dhubri", "Cachar", "Kokrajhar"]
    
    for a in areas:
        exists = db.query(models.Location).filter(models.Location.name == a).first()
        if not exists:
            db.add(models.Location(name=a))
    
    # 2. Create Grocery Items
    items_data = [
        {"name": "Assam Tea (CTC)", "unit": "kg", "base": 250.0},
        {"name": "Fresh River Fish (Rohu)", "unit": "kg", "base": 200.0},
        {"name": "Basmati Rice (Premium)", "unit": "kg", "base": 135.0},
        {"name": "Local Chicken (Free Range)", "unit": "kg", "base": 280.0},
        {"name": "Fresh Milk (Buffalo)", "unit": "liter", "base": 65.0},
        {"name": "Fresh Tomatoes", "unit": "kg", "base": 38.0},
        {"name": "Fresh Potatoes", "unit": "kg", "base": 25.0},
        {"name": "Fresh Farm Eggs", "unit": "piece", "base": 7.5},
        {"name": "Assam Rice (Local)", "unit": "kg", "base": 70.0},
        {"name": "Mustard Oil (Cold Pressed)", "unit": "liter", "base": 175.0}
    ]
    
    for i in items_data:
        exists = db.query(models.Item).filter(models.Item.name == i["name"]).first()
        if not exists:
            db.add(models.Item(name=i["name"], unit=i["unit"]))
    
    # 3. Create Users (Admin & SeedBot)
    bot_email = "bot@yourlocal.com"
    exists = db.query(models.User).filter(models.User.email == bot_email).first()
    if not exists:
        db.add(models.User(email=bot_email, role="bot", hashed_password="seed_password_123"))
    
    db.commit() # Save Parents first to get IDs
    
    # --- B. GENERATE 6 MONTHS OF PRICE HISTORY ---
    print("Generating 6 months of historical market data...")
    
    # Use timezone-aware UTC datetime and strip time for clean day-by-day series
    today = datetime.datetime.now(datetime.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - datetime.timedelta(days=180)
    all_entries = []

    # Get the fresh IDs from the DB
    db_items_list = db.query(models.Item).all()
    db_locations_list = db.query(models.Location).all()
    db_bot = db.query(models.User).filter(models.User.role == "bot").first()

    if not db_bot:
        print("Error: Seed bot user not found.")
        db.close()
        return

    for item_meta in items_data:
        db_item = next((i for i in db_items_list if i.name == item_meta["name"]), None)
        if not db_item:
            continue
        
        base_price = float(item_meta["base"])

        for loc in db_locations_list:
            
            # Generate data for every 2nd day
            for day in range(0, 180, 2):
                current_time = start_date + datetime.timedelta(days=day)
                
                # MARKET SIMULATION FORMULA:
                trend = day * 0.05 
                seasonality = 12 * math.sin(2 * math.pi * day / 30)
                noise = random.uniform(-3, 3)
                
                # FINAL PRICE CALCULATION:
                # We use max(0.5, ...) to ensure price never goes negative for cheap items
                final_price = round(max(0.5, base_price + trend + seasonality + noise), 2)
                
                entry = models.PriceEntry(
                    item_id=db_item.id,
                    location_id=loc.id,
                    user_id=db_bot.id,
                    price=final_price,
                    distance_miles=round(random.uniform(0.1, 2.5), 1),
                    votes=random.randint(20, 55),
                    status="APPROVED",
                    timestamp=current_time
                )
                all_entries.append(entry)

    print(f"Uploading {len(all_entries)} price points...")
    db.bulk_save_objects(all_entries)
    db.commit()
    
    print("\n" + "="*30)
    print("SUCCESS: Your Database is now SEEDED!")
    print(f"Seeded: {len(db_items_list)} Items")
    print(f"Seeded: {len(db_locations_list)} Locations")
    print(f"Seeded: {len(all_entries)} Historical Data Points")
    print("="*30)
    
    db.close()

if __name__ == "__main__":
    seed_data()
