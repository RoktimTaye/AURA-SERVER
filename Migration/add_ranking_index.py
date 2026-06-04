from sqlalchemy import create_engine, text
import sys
import os

# Add the parent directory (AURA/server) to sys.path so we can import from 'app'
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    from app.database import SQLALCHEMY_DATABASE_URL
except ImportError:
    print("Error: Could not import app.database. Ensure you are running this from AURA/server directory.")
    sys.exit(1)

engine = create_engine(SQLALCHEMY_DATABASE_URL)

def run_migration():
    """
    Creates the compound index for optimized ranking and pagination.
    This acts as a 'Virtual Sorted Table'.
    """
    with engine.connect() as conn:
        print("Running Migration: Adding compound ranking index...")
        try:
            # item_id, location_id: for fast filtering
            # votes, id: for deterministic, non-duplicate sorting
            sql = "CREATE INDEX IF NOT EXISTS idx_ranking_v2 ON price_entries (item_id, location_id, votes DESC, id DESC);"
            conn.execute(text(sql))
            conn.commit()
            print("SUCCESS: Index 'idx_ranking_v2' created or already exists.")
        except Exception as e:
            print(f"FAILURE: Error creating index: {e}")

if __name__ == "__main__":
    run_migration()
