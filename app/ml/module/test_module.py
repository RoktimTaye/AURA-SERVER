import logging
from app.ml.module.pipeline import process_single_task
from app.ml.module.data_loader import DataLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_modular_pipeline():
    # Use CSV mode since DB is unreachable
    loader = DataLoader(use_db=False)
    pairs = loader.get_active_pairs()
    
    if not pairs:
        logger.warning("No active pairs found in CSV. Test skipped.")
        return

    logger.info(f"Testing pipeline with first pair: {pairs[0]}")
    item_id, district = pairs[0]
    
    # Run in fast mode and CSV mode
    results = process_single_task(item_id, district, fast_mode=True, use_db=False)
    
    if results:
        logger.info(f"✅ Success! Generated {len(results)} forecast entries.")
        logger.info(f"Sample: {results[0]}")
    else:
        logger.warning("❌ Failed to generate forecasts. Check if enough data exists (min 10 points).")

if __name__ == "__main__":
    test_modular_pipeline()
