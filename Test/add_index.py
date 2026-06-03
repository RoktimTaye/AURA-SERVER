from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database import SQLALCHEMY_DATABASE_URL

engine = create_engine(SQLALCHEMY_DATABASE_URL)

def add_index():
    with engine.connect() as conn:
        print("Adding index on status and timestamp...")
        try:
            conn.execute(text("CREATE INDEX idx_status_timestamp ON price_entries (status, timestamp DESC);"))
            conn.commit()
            print("Index added successfully.")
        except Exception as e:
            print(f"Index might already exist or error: {e}")

if __name__ == "__main__":
    add_index()
