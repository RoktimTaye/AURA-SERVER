import time
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add the app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import models
from app.database import SQLALCHEMY_DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def profile_optimised_query():
    db = SessionLocal()
    try:
        print("Profiling Optimized Directory Query...")
        
        # Original slow version
        start_time = time.time()
        query_slow = db.query(
            models.PriceEntry.id,
            models.Item.name,
            models.Item.unit,
            models.PriceEntry.price,
            models.Location.district,
            models.Location.name,
            models.PriceEntry.votes,
            models.PriceEntry.status,
            models.PriceEntry.timestamp,
            func.min(models.PriceEntry.price),
            func.max(models.PriceEntry.price)
        ).join(models.Item).join(models.Location).filter(models.PriceEntry.status == "APPROVED")\
         .group_by(models.PriceEntry.id, models.Item.name, models.Item.unit, models.Location.district, models.Location.name)\
         .order_by(models.PriceEntry.timestamp.desc()).limit(100)
        _ = query_slow.all()
        print(f"Time for Slow Query: {time.time() - start_time:.4f} seconds")

        # Optimized version (No aggregates, no group by)
        start_time = time.time()
        query_fast = db.query(
            models.PriceEntry.id,
            models.Item.name,
            models.Item.unit,
            models.PriceEntry.price,
            models.Location.district,
            models.Location.name,
            models.PriceEntry.votes,
            models.PriceEntry.status,
            models.PriceEntry.timestamp
        ).join(models.Item).join(models.Location).filter(models.PriceEntry.status == "APPROVED")\
         .order_by(models.PriceEntry.timestamp.desc()).limit(100)
        _ = query_fast.all()
        print(f"Time for Fast Query: {time.time() - start_time:.4f} seconds")

    finally:
        db.close()

if __name__ == "__main__":
    profile_optimised_query()
