import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database import SQLALCHEMY_DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)

def profile():
    with engine.connect() as conn:
        print("Running EXPLAIN ANALYZE...")
        result = conn.execute(text("""
            EXPLAIN ANALYZE
            SELECT price_entries.id, items.name AS item_name, items.unit, price_entries.price AS price_modal, locations.district, locations.name AS market_name, price_entries.votes, price_entries.status, price_entries.timestamp, price_entries.item_id 
            FROM price_entries JOIN items ON items.id = price_entries.item_id JOIN locations ON locations.id = price_entries.location_id 
            WHERE price_entries.status = 'APPROVED' 
            ORDER BY price_entries.timestamp DESC
             LIMIT 100 OFFSET 0
        """))
        for row in result:
            print(row[0])

if __name__ == "__main__":
    profile()
