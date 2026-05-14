from app.database import engine
from sqlalchemy import text

def update_schema():
    with engine.connect() as conn:
        print("Dropping old unique constraint if it exists...")
        # SQLAlchemy creates 'ix_locations_name' as a unique index for unique=True
        # We need to drop it and add our new composite constraint.
        try:
            conn.execute(text("DROP INDEX IF EXISTS ix_locations_name;"))
            conn.execute(text("ALTER TABLE locations DROP CONSTRAINT IF EXISTS locations_name_key;"))
            conn.commit()
            print("Dropped old constraints.")
        except Exception as e:
            print(f"Error dropping constraints: {e}")

        print("Creating new composite unique constraint...")
        try:
            # Note: We already updated the model, so Base.metadata.create_all(engine) 
            # might try to do this, but it doesn't handle existing tables well for migrations.
            # We'll do it manually to be sure.
            conn.execute(text("ALTER TABLE locations ADD CONSTRAINT _location_uc UNIQUE (name, district, state);"))
            conn.commit()
            print("Added new composite constraint.")
        except Exception as e:
            print(f"Error adding new constraint: {e}")

if __name__ == "__main__":
    update_schema()
