import pandas as pd
import logging
from sqlalchemy import text
from app.database import SessionLocal, engine
from app import models

logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, use_db=True):
        self.use_db = use_db

    def load_data(self, item_id=None, district=None):
        """
        Loads data from DB or local CSV.
        If item_id and district are provided, fetches only that subset.
        """
        if self.use_db:
            return self._load_from_db(item_id, district)
        else:
            return self._load_from_csv(item_id, district)

    def _load_from_db(self, item_id=None, district=None):
        db = SessionLocal()
        try:
            query = db.query(
                models.PriceEntry.item_id,
                models.Location.district,
                models.PriceEntry.price.label('y'),
                models.PriceEntry.timestamp.label('ds')
            ).join(models.Location).filter(models.PriceEntry.status == "APPROVED")

            if item_id:
                query = query.filter(models.PriceEntry.item_id == item_id)
            if district:
                query = query.filter(models.Location.district == district)

            df = pd.read_sql(query.statement, engine)
            return df
        except Exception as e:
            logger.error(f"Error loading from DB: {e}")
            return pd.DataFrame()
        finally:
            db.close()

    def _load_from_csv(self, item_id=None, district=None, filepath='Dataset2.csv'):
        try:
            df = pd.read_csv(filepath)
            
            # WFP Kaggle datasets often have an 'HXL' tag row right after the header. Remove it.
            if df.iloc[0]['date'] == '#date':
                df = df.iloc[1:].copy()

            # Basic renaming for consistency
            column_mapping = {
                'date': 'ds',
                'price': 'y',
                'admin2': 'district',
                'commodity': 'item_name'
            }
            df = df.rename(columns=column_mapping)
            df['ds'] = pd.to_datetime(df['ds'])
            df['y'] = pd.to_numeric(df['y'], errors='coerce')

            if item_id:
                df = df[df['item_name'] == item_id]
            if district:
                df = df[df['district'] == district]

            return df
        except Exception as e:
            logger.error(f"Error loading from CSV: {e}")
            return pd.DataFrame()

    def get_active_pairs(self):
        """Returns list of (item_id, district) pairs."""
        if self.use_db:
            db = SessionLocal()
            try:
                pairs = db.execute(text("""
                    SELECT DISTINCT pe.item_id, l.district 
                    FROM price_entries pe 
                    JOIN locations l ON pe.location_id = l.id 
                    WHERE pe.status = 'APPROVED'
                """)).fetchall()
                return [(int(p[0]), p[1]) for p in pairs]
            finally:
                db.close()
        else:
            # For CSV, we'll use item_name and district as identifiers
            df = self._load_from_csv()
            if df.empty:
                return []
            pairs = df.groupby(['item_name', 'district']).size().reset_index()
            # Return item_name as the ID for CSV mode
            return list(zip(pairs['item_name'], pairs['district']))
