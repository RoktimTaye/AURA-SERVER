from sqlalchemy import text
from app.database import engine

def apply_indexes():
    """
    Applies composite indexes to the database to speed up ML data fetching.
    """
    commands = [
        # Composite index for PriceEntry status, item, location, and timestamp
        # This allows the query in the pipeline to be a "covering index" scan
        "CREATE INDEX IF NOT EXISTS idx_price_entries_optimized ON price_entries (status, item_id, location_id, timestamp);",
        
        # Index for faster retrieval of distinct pairs
        "CREATE INDEX IF NOT EXISTS idx_price_entries_pairs ON price_entries (status, item_id, location_id);"
    ]
    
    with engine.connect() as connection:
        for cmd in commands:
            print(f"Executing: {cmd}")
            connection.execute(text(cmd))
        print("✅ Indexes applied successfully.")

if __name__ == "__main__":
    apply_indexes()
